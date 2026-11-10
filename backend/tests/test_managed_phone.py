import base64
from datetime import timedelta

import pytest
from conftest import make_call
from semantic_fixture import bind
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.db import session
from brightwater.managed.engine import Conversation, managed_error
from brightwater.managed.phone import caller_evidence
from brightwater.managed.plivo import Response, SpeechClock, alignment_complete
from brightwater.managed.readback import complete_readback
from brightwater.policy import Rejected, explicit_yes, now


def event(db, call, kind, at, **payload):
    return svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind=kind,
        occurred_at=at, payload=payload))


def phone(db):
    call, token = make_call(db, verified=False)
    call.purpose = "engineering"
    db.flush()
    conv = Conversation(call.id, trusted_phone=True)
    base = now() - timedelta(seconds=8)
    event(db, call, "turn_state", base, source="identity_question", text="Am I speaking with Helen Price?",
          name="Helen Price", completed=True, notice_delivered=True)
    event(db, call, "agent_utterance", base + timedelta(seconds=.1), source="plivo_elevenlabs_observer",
          text="Am I speaking with Helen Price?", playback_completed=True, interrupted=False)
    event(db, call, "user_utterance", base + timedelta(seconds=1), source="plivo_elevenlabs_observer",
          text="Yes, you are", speech_timing_verified=True)
    conv.agent("Am I speaking with Helen Price?")
    conv.user("Yes, you are")
    bind(db, conv, identity="assent", identity_question=True)
    assert conv.execute(db, "confirm_identity", {}, "identity")["verified"] is True
    conv.understanding = None
    offers = conv.execute(db, "check_availability", {"items": [{"property_id": "BW-1041-P1", "service": "service"}]}, "availability")
    prepared = conv.execute(db, "prepare_booking", {"offer_id": offers["options"][0]["offer_id"], "tenants": []}, "prepare")
    proposal = db.get(m.Proposal, prepared["proposal_id"])
    proposal.created_at = now() - timedelta(seconds=4)
    return call, conv, prepared


@pytest.mark.parametrize("answer", ["Yeah, yeah, yeah, yeah, sure.", "Yes, do it.", "Yes, book it. Yes, book it."])
def test_exact_owner_replies_are_whole_utterance_agreement(answer):
    assert explicit_yes(answer)


@pytest.mark.parametrize("answer", ['He said "yes book it"', "Yes, but change the day", "Sure, no, cancel it", "Yes, book it, but not Monday"])
def test_corrections_and_quoted_agreement_still_fail(answer):
    assert not explicit_yes(answer)


def test_channel_restriction_does_not_blame_customer_or_request_another_yes():
    result = managed_error(Rejected("managed_audio_unqualified", "old internal message"), agreement_present=True)
    assert result["retryable"] is False
    assert result["customer_confirmation_needed"] is False
    assert "already given agreement" in result["instruction"]
    assert "never ask them to say yes again" in result["instruction"].lower()


def test_managed_phone_reserves_with_real_policy_guard_and_exact_owner_reply():
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        db.get(m.Property, "BW-1041-P1").boiler_year = 2020
        readback_at = now() - timedelta(seconds=2)
        event(db, call, "agent_utterance", readback_at, source="plivo_elevenlabs_observer",
              text=prepared["readback"], playback_completed=True, interrupted=False)
        reply = "Yeah, yeah, yeah, yeah, sure."
        event(db, call, "user_utterance", now() - timedelta(seconds=1), source="plivo_elevenlabs_observer",
              text=reply, speech_timing_verified=True)
        conv.agent(prepared["readback"])
        conv.user(reply)
        bind(db, conv, appointment="confirm")
        result = conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, "commit")
        assert result["confirmed"] is True
        assert result["close_with_native_end_call"] is True
        assert call.state == "in_progress", "Carrier lifecycle, rather than a redundant LLM finish request, ends the phone record"
        assert result["evidence_contract"] == "carrier_playout_and_original_speech"
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 1
        conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, "commit-retry")
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 1
        event(db, call, "ended", now(), source="signed_plivo_status", carrier_answered=True)
        assert call.state == "finished" and call.outcome == "Booked"
        assert call.summary == "A confirmed booking is saved in the diary. Review its visit details and the recording below."


@pytest.mark.parametrize("failure", ["early_reply", "queued_only", "interrupted", "no_timing", "wrong_source", "no_postcode"])
def test_phone_booking_never_bypasses_original_speech_and_playout(failure):
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        db.get(m.Property, "BW-1041-P1").boiler_year = 2020
        readback_at = now() - timedelta(seconds=2)
        readback = prepared["readback"].replace(", PO4 0JT", "") if failure == "no_postcode" else prepared["readback"]
        event(db, call, "agent_utterance", readback_at, source="plivo_elevenlabs_observer", text=readback,
              playback_completed=failure != "queued_only", interrupted=failure == "interrupted")
        reply = "Yes, do it."
        event(db, call, "user_utterance", readback_at + timedelta(seconds=-.1 if failure == "early_reply" else 1),
              source="untrusted" if failure == "wrong_source" else "plivo_elevenlabs_observer",
              text=reply, speech_timing_verified=failure != "no_timing")
        conv.agent(readback)
        conv.user(reply)
        from brightwater.managed.intent import IntentEvidence
        row = db.get(m.Proposal, prepared["proposal_id"])
        conv.intent = IntentEvidence(call.id, row.id, row.fingerprint, readback, reply, "confirm")
        with pytest.raises(Rejected):
            conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, "commit")
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


def test_spoken_words_match_details_but_missing_postcode_still_fails():
    with session() as db, db.begin():
        _, _, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared["proposal_id"])
        spoken = prepared["readback"].replace("18", "eighteen").replace("16th", "sixteenth").replace("£95", "ninety-five pounds")
        assert complete_readback(spoken, proposal)
        assert not complete_readback(spoken.replace("PO4 0JT", ""), proposal)
        assert not complete_readback(spoken.replace("ninety-five", "one hundred and ninety-five"), proposal)


def test_original_packet_clock_survives_late_processing_and_deduplicates():
    from livekit import rtc
    clock = SpeechClock()
    frame = rtc.AudioFrame(bytes(320), 8000, 1, 160, userdata={"received_at": 100.0})
    clock.frame(frame)
    clock.speech(160, .01)
    original = clock.transcript(7)
    assert original is not None and original <= 100
    assert clock.transcript(7) is None
    assert clock.transcript(8) == original
    clock.end_turn(8)
    assert clock.transcript(9) is None


@pytest.mark.parametrize("late_end", [False, True])
def test_completed_preopening_speech_does_not_poison_first_identity_reply(late_end):
    from livekit import rtc
    clock = SpeechClock()
    for index in range(220):
        clock.frame(rtc.AudioFrame(bytes(320), 8000, 1, 160,
            userdata={"received_at": 1000 + (index + 1) * .02}))
    clock.speech(3 * 16000, .064, sample_rate=16000)
    if not late_end:
        clock.end_speech(4 * 16000, sample_rate=16000)
    clock.begin_opening(1004.3)
    if late_end:
        clock.end_speech(4 * 16000, sample_rate=16000)
    clock.end_turn(1)
    for index in range(220, 750):
        clock.frame(rtc.AudioFrame(bytes(320), 8000, 1, 160,
            userdata={"received_at": 1000 + (index + 1) * .02}))
    clock.speech(15 * 16000, .064, sample_rate=16000)
    original = clock.transcript(94)
    assert 1014.8 < original < 1015.1
    assert clock.preopening_discarded == 1
    assert clock.transcript(95) == original  # split ASR keeps original onset


@pytest.mark.parametrize("end_index", [None, 6 * 16000])
def test_speech_overlapping_opening_keeps_early_original_onset(end_index):
    from livekit import rtc
    clock = SpeechClock()
    for index in range(300):
        clock.frame(rtc.AudioFrame(bytes(320), 8000, 1, 160,
            userdata={"received_at": 1000 + (index + 1) * .02}))
    clock.speech(3 * 16000, .064, sample_rate=16000)
    clock.begin_opening(1004.3)
    if end_index:
        clock.end_speech(end_index, sample_rate=16000)
    for index in range(300, 750):
        clock.frame(rtc.AudioFrame(bytes(320), 8000, 1, 160,
            userdata={"received_at": 1000 + (index + 1) * .02}))
    clock.speech(15 * 16000, .064, sample_rate=16000)
    assert clock.transcript(94) < 1004.3
    assert clock.preopening_discarded == 0


@pytest.mark.parametrize("answer,meaning", [
    ("Yes, I am", "assent"), ("Yes, you are", "assent"),
    ("Yes, I am Samudra Banerjee.", "self"),
])
def test_first_identity_reply_after_opening_uses_existing_contextual_identity_guard(answer, meaning):
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        call.purpose = "engineering"
        db.get(m.Customer, call.customer_id).name = "Samudra Banerjee"
        base = now() - timedelta(seconds=20)
        greeting = "I'm Brightwater's AI assistant. This is a recorded engineering test using fictional details. Am I speaking with Samudra Banerjee?"
        event(db, call, "turn_state", base + timedelta(seconds=4.2),
            source="managed_agent_prompt", completed=False, native_event_id=1, revision=1)
        event(db, call, "agent_utterance", base + timedelta(seconds=14.496),
            source="plivo_elevenlabs_observer", text=greeting, playback_completed=True,
            interrupted=False, native_event_id=1, revision=1)
        event(db, call, "turn_state", base + timedelta(seconds=14.496),
            source="identity_question", completed=True, notice_delivered=True)
        event(db, call, "user_utterance", base + timedelta(seconds=15.008),
            source="plivo_elevenlabs_observer", text=answer, speech_timing_verified=True)
        conv = Conversation(call.id, trusted_phone=True)
        conv.agent(greeting)
        conv.user(answer)
        bind(db, conv, identity=meaning, identity_question=True)
        assert conv.execute(db, "confirm_identity", {}, "first-reply")["verified"] is True


def test_alignment_requires_final_character_without_treating_caption_estimates_as_audio_clock():
    response = Response(1, "Shall I book it?")
    audio = {"audio_base_64": base64.b64encode(bytes(32000)).decode(),
             "alignment": {"chars": list("Shall I "), "char_start_times_ms": [0] * 8, "char_durations_ms": [1] * 8}}
    assert not alignment_complete(response, audio)
    audio["alignment"] = {"chars": list("book it?"), "char_start_times_ms": [0] * 8, "char_durations_ms": [1] * 8}
    assert alignment_complete(response, audio)
    short = Response(2, "Yes")
    audio["alignment"] = {"chars": list("Yes"), "char_start_times_ms": [0] * 3, "char_durations_ms": [2000] * 3}
    assert alignment_complete(short, audio)
    # Caption completion alone is never persisted as played: the transport
    # integration test below still requires the final carrier checkpoint ACK.


def test_provider_history_alone_cannot_supply_phone_identity_evidence():
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        call.purpose = "engineering"
        conv = Conversation(call.id, trusted_phone=True)
        conv.agent("Am I speaking with Helen Price?")
        conv.user("Yes")
        with pytest.raises(Rejected):
            conv.execute(db, "confirm_identity", {}, "identity")
        assert not call.identity_verified
        with pytest.raises(Rejected):
            caller_evidence(db, call, "Yes")


def test_phone_profile_uses_qualified_pcm_alignment_without_changing_carrier_format():
    from brightwater.managed.agent import config
    browser = config()
    phone = config(phone=True)
    assert browser["conversation_config"]["tts"]["agent_output_audio_format"] == "pcm_16000"
    assert phone["conversation_config"]["tts"]["agent_output_audio_format"] == "pcm_16000"
    assert phone["conversation_config"]["asr"]["user_input_audio_format"] == "pcm_16000"
    assert phone["platform_settings"]["auth"]["enable_auth"] is True


def test_real_transport_only_emits_completed_managed_speech_after_final_checkpoint():
    import asyncio

    from test_plivo_audio import ack, drained, ready

    from brightwater.managed.plivo import ManagedPlivo

    class Provider:
        async def __aiter__(self):
            text = "Am I speaking with Helen Price?"
            yield {"type": "agent_response", "agent_response_event": {"event_id": 1, "agent_response": text}}
            yield {"type": "audio", "audio_event": {"event_id": 1, "audio_base_64": base64.b64encode(bytes(640)).decode(),
                "alignment": {"chars": list(text), "char_start_times_ms": [0] * len(text), "char_durations_ms": [1] * len(text)}}}

    async def scenario():
        transport, ws = await ready()
        async def emit(*args, **kwargs):
            pass
        bridge = ManagedPlivo(transport, Provider(), customer_name="Helen Price", emit=emit)
        output = asyncio.create_task(bridge.output_audio())
        try:
            await bridge.receive()
            await asyncio.wait_for(bridge.output.join(), 2)
            for _ in range(100):
                if all(r.flushed for r in bridge.responses.values()):
                    break
                await asyncio.sleep(.005)
            assert all(r.flushed for r in bridge.responses.values())
            await drained(transport)
            pending = bridge.audit.get_nowait()
            assert pending[0] == 'turn_state' and pending[1]['completed'] is False
            assert bridge.audit.empty()
            final = [item for item in ws.sent if item["event"] == "checkpoint"][-1]
            await transport.handle_message(ack(final["name"]))
            kind, payload, _, _ = bridge.audit.get_nowait()
            assert kind == "agent_utterance" and payload["playback_completed"] is True
        finally:
            output.cancel()
            await asyncio.gather(output, return_exceptions=True)
            await bridge.vad_stream.aclose()
            await transport.aclose()
    asyncio.run(scenario())


def test_interruption_discards_remaining_chunks_and_late_ack_cannot_complete_readback():
    import asyncio

    from test_plivo_audio import ack, drained, ready

    from brightwater.managed.plivo import ManagedPlivo

    async def scenario():
        transport, ws = await ready(max_buffered_seconds=.02)
        async def emit(*args, **kwargs):
            pass
        bridge = ManagedPlivo(transport, None, customer_name="Helen Price", emit=emit)
        response = Response(1, text="Prepared full readback", complete=True, bytes_received=20000)
        bridge.responses[1] = response
        bridge.queued_bytes = 20000
        bridge.output.put_nowait((0, response, bytes([255]) * 20000, True))
        output = asyncio.create_task(bridge.output_audio())
        try:
            for _ in range(50):
                if any(v["event"] == "checkpoint" for v in ws.sent):
                    break
                await asyncio.sleep(.002)
            first = next(v for v in ws.sent if v["event"] == "checkpoint")
            bridge.interrupt()
            await transport.handle_message({"event": "clearedAudio", "sequenceNumber": 2, "streamId": "stream"})
            await transport.handle_message(ack(first["name"], 3))
            await asyncio.wait_for(bridge.output.join(), 2)
            await drained(transport)
            clear = next(i for i, item in enumerate(ws.sent) if item["event"] == "clearAudio")
            assert not any(item["event"] == "playAudio" for item in ws.sent[clear + 1:])
            proofs = []
            while not bridge.audit.empty():
                proofs.append(bridge.audit.get_nowait())
            assert not any(p[0] == "agent_utterance" and p[1]["playback_completed"] for p in proofs)
        finally:
            output.cancel()
            await asyncio.gather(output, return_exceptions=True)
            await bridge.vad_stream.aclose()
            await transport.aclose()
    asyncio.run(scenario())


def test_native_g711_bridge_preserves_all_quantised_sample_values():
    import audioop
    raw = bytes(range(256))
    decoded = audioop.ulaw2lin(raw, 2)
    encoded = audioop.lin2ulaw(decoded, 2)
    assert audioop.ulaw2lin(encoded, 2) == decoded


def test_gateway_admission_and_unsigned_checks_remain_for_native_backend():
    from fastapi.testclient import TestClient
    from test_plivo_gateway import config

    from brightwater.plivo_gateway import create_app
    app = create_app(config(voice_backend="elevenlabs", gateway_enabled=False))
    assert app.state is not None
    response = TestClient(app).post("/v1/outbound", json={"call_id": "11111111-1111-1111-1111-111111111111",
        "phone": "+919876543210", "session_token": "not-real", "purpose": "engineering"})
    assert response.status_code == 401


def test_main_call_retains_carrier_request_id_when_managed_conversation_binds():
    from brightwater.managed.gateway import bind_conversation
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose = "engineering"
        call.provider_id = "carrier-request-uuid"
        bind_conversation(db, call, "conv_fixture", phone=True)
        bind_conversation(db, call, "conv_fixture", phone=True)
        db.flush()
        assert call.provider_id == "carrier-request-uuid"
        assert db.scalar(select(func.count()).select_from(m.CallEvent).where(m.CallEvent.call_id == call.id,
            m.CallEvent.kind == "managed_session")) == 1


def test_non_phone_evaluation_is_never_misclassified_as_an_unanswered_phone_call():
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        call.purpose = "managed_evaluation"
        svc.finalise(db, call, "Non-phone evaluation finished without a business result.")
        assert call.outcome is None


def test_native_gateway_does_not_need_model_account_keys_on_the_carrier_host():
    from test_plivo_gateway import config
    cfg = config(voice_backend="elevenlabs", openai_api_key="", elevenlabs_api_key="")
    assert cfg.voice_backend == "elevenlabs"


def test_managed_phone_session_requires_both_scoped_call_and_trusted_gateway(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from brightwater.api import app
    from brightwater.config import settings
    cfg = settings()
    for key, value in {"managed_enabled": True, "managed_phone_enabled": True,
        "managed_agent_id": "agent_browser_fixture", "managed_phone_agent_id": "agent_phone_fixture",
        "managed_api_key": SecretStr("test-not-real"), "managed_webhook_secret": SecretStr("s" * 40)}.items():
        monkeypatch.setattr(cfg, key, value)
    with session() as db, db.begin():
        call, token = make_call(db)
        call.purpose = "engineering"
    with TestClient(app) as client:
        assert client.post("/runtime/managed/session").status_code == 401
        assert client.post("/runtime/managed/session", headers={"Authorization": "Bearer " + token}).status_code == 401
        # Correct double credentials still cannot attach a different destination.
        response = client.post("/runtime/managed/session", headers={"Authorization": "Bearer " + token,
            "X-Brightwater-Runtime": cfg.runtime_token.get_secret_value()})
        assert response.status_code == 403


def test_unavailable_voice_route_does_not_claim_ambiguous_words_were_agreement():
    result = managed_error(Rejected("managed_audio_unqualified", "Internal gate"), agreement_present=False)
    assert result["caller_agreed"] is False
    assert "already given agreement" not in result["instruction"]
    assert result["customer_confirmation_needed"] is False


def test_eight_early_tool_readers_wait_for_the_same_original_speech_without_locking_writer(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from brightwater.managed import phone as adapter
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose = "engineering"
        call_id = call.id
    original = now() - timedelta(seconds=2)
    missing = threading.Barrier(9)
    released = threading.Event()
    seen = threading.local()
    actual = adapter.caller_evidence
    def forced(db, call, text):
        try:
            return actual(db, call, text)
        except Rejected:
            if not getattr(seen, "missing", False):
                seen.missing = True
                missing.wait(timeout=3)
                released.wait(timeout=3)
            raise
    monkeypatch.setattr(adapter, "caller_evidence", forced)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(adapter.wait_for_caller, session, call_id, "Yes, book it", 3) for _ in range(8)]
        try:
            missing.wait(timeout=3)
            with session() as db, db.begin():
                call = db.get(m.Call, call_id)
                event(db, call, "user_utterance", original, source="plivo_elevenlabs_observer",
                      text="Yes, book it", speech_timing_verified=True)
        finally:
            released.set()
        assert all(f.result(timeout=4) is True for f in futures)
    with session() as db:
        source = actual(db, db.get(m.Call, call_id), "Yes, book it")
        assert source.occurred_at == original


def test_callback_yes_is_contextual_and_cannot_be_taken_from_booking_or_overrule_refusal():
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose = "managed_evaluation"
        conv = Conversation(call.id, text_only=True)
        conv.agent("Would you like me to record a callback request?")
        conv.user("Yes please")
        bind(db, conv, followup="callback", followup_basis="contextual")
        assert conv.followup_requested("Yes please", "callback")
        conv.agent("Shall I book that appointment for you?")
        conv.user("Yes please")
        bind(db, conv)
        assert not conv.followup_requested("Yes please", "callback")
        conv.user("I don't want a callback, I want the service booked")
        conv.agent("Would you like a callback?")
        conv.user("Yes please")
        assert not conv.followup_requested("Yes please", "callback")
        conv.user("Please call me back")
        bind(db, conv, followup="callback", followup_basis="explicit", rescinds_callback_refusal=True)
        assert conv.followup_requested("Please call me back", "callback")


def test_split_native_asr_keeps_original_onset_and_rejects_late_prior_turn():
    clock = SpeechClock()
    clock.starts.extend([100.0, 101.2])
    assert clock.transcript(71) == 100.0
    assert clock.transcript(81) == 100.0
    clock.end_turn(81)
    clock.starts.append(110.0)
    assert clock.transcript(75) is None  # late unseen transcript cannot consume new speech
    assert clock.transcript(90) == 110.0
    clock.end_turn(90)
    assert clock.transcript(91) is None


def test_phone_quality_never_hides_consent_or_adds_speech_before_commit():
    from brightwater.managed.agent import config
    phone = config('kb', 'https://example.test', 'provider-secret', phone=True)
    browser = config('kb', 'https://example.test', 'provider-secret')
    tools = {t['name']: t for t in phone['conversation_config']['agent']['prompt']['tools']}
    assert tools['check_availability']['pre_tool_speech'] == 'force'
    assert tools['prepare_booking']['pre_tool_speech'] == 'off'
    assert tools['record_followup']['pre_tool_speech'] == 'force'
    for name in ['confirm_identity', 'confirm_booking', 'cancel_arrangement', 'finish_conversation']:
        assert tools[name]['pre_tool_speech'] == 'off'
    assert phone['conversation_config']['turn']['interruption_ignore_terms'] == []
    assert not set(browser['conversation_config']['turn']['interruption_ignore_terms']) & {'yes', 'no', 'stop', 'cancel'}


@pytest.mark.parametrize("late_text,settled", [(False, False), (True, False), (True, True)])
def test_pretool_and_answer_share_event_id_without_mixing_audio_or_losing_trailing_pcm(late_text, settled):
    import asyncio

    from test_plivo_audio import ack, drained, ready

    from brightwater.managed.plivo import ManagedPlivo

    class Provider:
        async def __aiter__(self):
            for response_id, text in [("checking", "Let me check the diary."),
                                      ("result", "Monday morning is available.")]:
                caption = {"type": "agent_response", "agent_response_event": {
                    "event_id": 9, "response_id": response_id, "agent_response": text}}
                if not (late_text and response_id == "result"):
                    yield caption
                yield {"type": "audio", "audio_event": {"event_id": 9,
                    "audio_base_64": base64.b64encode(bytes(640)).decode(), "is_final": False,
                    "alignment": {"chars": list(text), "char_start_times_ms": [0] * len(text),
                                  "char_durations_ms": [1] * len(text)}}}
                if late_text and response_id == "result":
                    yield caption
                # Actual provider wire: caption complete, followed by more PCM
                # with empty alignment and is_final still false.
                await asyncio.sleep(.03)
                yield {"type": "audio", "audio_event": {"event_id": 9,
                    "audio_base_64": base64.b64encode(bytes(640)).decode(), "is_final": False,
                    "alignment": {"chars": [], "char_start_times_ms": [], "char_durations_ms": []}}}
                if settled:
                    await asyncio.sleep(.25)

    async def scenario():
        transport, ws = await ready()
        async def emit(*args, **kwargs):
            pass
        bridge = ManagedPlivo(transport, Provider(), customer_name="Helen Price", emit=emit)
        output = asyncio.create_task(bridge.output_audio())
        try:
            await bridge.receive()
            await asyncio.wait_for(bridge.output.join(), 2)
            for _ in range(100):
                if all(r.flushed for r in bridge.responses.values()):
                    break
                await asyncio.sleep(.005)
            responses = list(bridge.responses.values())
            assert len(responses) == 1
            assert responses[0].text == "Let me check the diary. Monday morning is available."
            assert responses[0].complete and responses[0].flushed and responses[0].bytes_received == 2560
            await drained(transport)
            final_names = [name for name, checkpoint in transport._pending.items() if checkpoint.final]
            assert len(final_names) == (2 if settled else 1)
            pending = [bridge.audit.get_nowait() for _ in range(bridge.audit.qsize())]
            assert pending and all(p[0] == 'turn_state' and p[1]['completed'] is False for p in pending)
            for sequence, name in enumerate(final_names, 2):
                await transport.handle_message(ack(name, sequence))
            proofs = [bridge.audit.get_nowait()[1] for _ in final_names]
            assert proofs[-1]["text"] == responses[0].text
            if settled:
                assert proofs[0]["text"] == "Let me check the diary."
            assert all(p["playback_completed"] for p in proofs)
            assert sum(len(base64.b64decode(v["media"]["payload"])) for v in ws.sent if v["event"] == "playAudio") == 640
        finally:
            output.cancel()
            await asyncio.gather(output, return_exceptions=True)
            await bridge.vad_stream.aclose()
            await transport.aclose()
    asyncio.run(scenario())


def test_audio_arriving_during_flush_never_inherits_an_earlier_playback_proof(monkeypatch):
    import asyncio

    from livekit import rtc
    from test_plivo_audio import ack, drained, ready

    from brightwater.managed import plivo

    async def scenario():
        transport, ws = await ready()
        tail_started, resume_tail = asyncio.Event(), asyncio.Event()
        capture = transport.audio_output.capture_frame
        held = False

        async def capture_with_backpressure(frame):
            nonlocal held
            if frame.userdata.get("probe_tail") and not held:
                held = True
                tail_started.set()
                await resume_tail.wait()
            await capture(frame)

        transport.audio_output.capture_frame = capture_with_backpressure
        async def emit(*args, **kwargs):
            pass

        class Provider:
            async def __aiter__(self):
                for index, text in enumerate(["Checking the diary.", "Shall I book Monday morning?"]):
                    if index:
                        await tail_started.wait()
                    yield {"type": "agent_response", "agent_response_event": {
                        "event_id": 11, "response_id": str(index), "agent_response": text}}
                    yield {"type": "audio", "audio_event": {"event_id": 11,
                        "audio_base_64": base64.b64encode(bytes(640)).decode(),
                        "alignment": {"chars": list(text), "char_start_times_ms": [0] * len(text),
                                      "char_durations_ms": [1] * len(text)}}}
                    if index:
                        resume_tail.set()

        bridge = plivo.ManagedPlivo(transport, Provider(), customer_name="Helen Price", emit=emit)

        class Resampler:
            def __init__(self, *args, **kwargs):
                pass
            def push(self, frame):
                return [rtc.AudioFrame(bytes(320), 8000, 1, 160)]
            def flush(self):
                return [rtc.AudioFrame(bytes(160), 8000, 1, 80, userdata={"probe_tail": True})]

        monkeypatch.setattr(plivo.rtc, "AudioResampler", Resampler)
        output = asyncio.create_task(bridge.output_audio())
        try:
            await asyncio.wait_for(bridge.receive(), 2)
            await asyncio.wait_for(bridge.output.join(), 2)
            for _ in range(100):
                await asyncio.sleep(.005)
                if len([p for p in transport._pending.values() if p.final]) == 2:
                    break
            await drained(transport)
            finals = [name for name, item in transport._pending.items() if item.final]
            assert len(finals) == 2, "New audio lost its final checkpoint during an earlier flush"
            pending = [bridge.audit.get_nowait() for _ in range(bridge.audit.qsize())]
            assert pending and all(p[0] == 'turn_state' and p[1]['completed'] is False for p in pending)
            for sequence, name in enumerate(finals, 2):
                await transport.handle_message(ack(name, sequence))
            proofs = [bridge.audit.get_nowait()[1] for _ in finals]
            assert proofs[0]["text"] == "Checking the diary.", "A queued answer changed an earlier proof"
            assert proofs[1]["text"] == "Checking the diary. Shall I book Monday morning?"
            assert all(p["playback_completed"] for p in proofs)
        finally:
            output.cancel()
            await asyncio.gather(output, return_exceptions=True)
            await bridge.vad_stream.aclose()
            await transport.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [None, "playback_checkpoint_timeout"])
def test_transport_close_preserves_interrupted_evidence_and_exposes_failure(failure):
    import asyncio

    from livekit import rtc
    from test_plivo_audio import ready

    from brightwater.managed.plivo import ManagedPlivo
    from brightwater.plivo_audio import AudioTransportError

    class Provider:
        async def __aiter__(self):
            await asyncio.Event().wait()
            yield {}

    async def scenario():
        transport, _ = await ready()
        emitted = []
        async def emit(kind, payload, **kwargs):
            emitted.append((kind, payload))
        bridge = ManagedPlivo(transport, Provider(), customer_name="Helen Price", emit=emit)
        response = Response(1, text="Unfinished readback", complete=True)
        bridge.playing.append(response)
        await transport.audio_output.capture_frame(rtc.AudioFrame(bytes(320), 8000, 1, 160))
        transport.audio_output.flush()
        running = asyncio.create_task(bridge.run())
        await asyncio.sleep(.01)
        transport._fail(failure or "closed", failure=failure is not None)
        if failure:
            with pytest.raises(AudioTransportError, match=failure):
                await asyncio.wait_for(running, 2)
        else:
            await asyncio.wait_for(running, 2)
        proof = next(payload for kind, payload in emitted if kind == "agent_utterance")
        assert proof["interrupted"] is True and proof["playback_completed"] is False
        await transport.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("store_fails", [False, True])
def test_private_playback_diagnostic_is_encrypted_bounded_and_never_masks_failure(monkeypatch, store_fails):
    import asyncio
    import json
    import time
    from types import SimpleNamespace

    import httpx
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from brightwater.managed import plivo

    captured = []
    cipher = Fernet(Fernet.generate_key())

    class HTTP:
        async def post(self, *args, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", "https://api.example/runtime/managed/session"),
                json={"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?token=private-provider-cap",
                      "customer_name": "Fixture", "token": "private-tool-cap"})

    class Redis:
        async def set(self, key, value, **kwargs):
            if store_fails:
                raise OSError("Diagnostic store unavailable")
            captured.append((key, value, kwargs))

    class Socket:
        async def send(self, data):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class Bridge:
        def __init__(self, *args, **kwargs):
            self.playing = []
            self.responses = {i: Response(i, text="Private fixture readback") for i in range(40)}
        async def run(self):
            raise RuntimeError("Primary provider failure")

    monkeypatch.setattr(plivo, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(plivo, "ManagedPlivo", Bridge)
    app = SimpleNamespace(state=SimpleNamespace(http=HTTP(), redis=Redis(), store=SimpleNamespace(cipher=cipher), active_bridges={}))
    context = {"call_id": "fixture-call", "sid": "fixture-session", "created": time.time(),
               "session_token": "private-call-cap", "max_seconds": 180}
    cfg = SimpleNamespace(api_url="https://api.example", runtime_token=SecretStr("private-runtime-cap"))
    transport = SimpleNamespace(failure_reason="playback_checkpoint_timeout", close_reason="playback_checkpoint_timeout",
        failure_snapshot={"pending_checkpoints": 2, "unacknowledged_samples": 160})
    async def event(*args, **kwargs):
        pass
    with pytest.raises(RuntimeError, match="Primary provider failure"):
        asyncio.run(plivo.run_managed_phone(app, context, cfg, transport, event))
    if store_fails:
        assert captured == []
    else:
        key, value, kwargs = captured[0]
        assert key == "voice:managed-diagnostic:fixture-session" and kwargs["ex"] == 86400
        assert b"Private fixture readback" not in value
        decoded = cipher.decrypt(value)
        assert b"private-call-cap" not in decoded and b"private-provider-cap" not in decoded
        assert len(json.loads(decoded)["responses"]) == 32
        assert json.loads(decoded)["transport_failure_snapshot"] == transport.failure_snapshot


def test_16khz_detector_indices_keep_the_original_8khz_carrier_onset():
    from livekit import rtc
    clocks = [SpeechClock(), SpeechClock()]
    for clock in clocks:
        for index in range(100):
            clock.frame(rtc.AudioFrame(bytes(320), 8000, 1, 160,
                userdata={"received_at": 100 + (index + 1) * .02}))
    assert clocks[0].speech(12000, .08, sample_rate=8000)
    assert clocks[1].speech(24000, .08, sample_rate=16000)
    assert clocks[0].transcript(7) == clocks[1].transcript(7)
    assert 101.3 < clocks[1].turn_start < 101.5
    # A delayed callback outside the retained original packet window cannot
    # become current speech by taking a transcript-arrival timestamp.
    assert not SpeechClock().speech(24000, .08, sample_rate=16000)


def test_local_detector_and_hosted_asr_receive_identical_16khz_audio(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from livekit import rtc

    from brightwater.managed import plivo

    frames, sent, load_options = [], [], []
    class Stream:
        def push_frame(self, frame):
            frames.append(frame)
        async def aclose(self):
            pass
    class Detector:
        def stream(self):
            return Stream()
    def load(**kwargs):
        load_options.append(kwargs)
        return Detector()
    monkeypatch.setattr(plivo.silero.VAD, "load", load)

    async def incoming():
        for index in range(10):
            yield rtc.AudioFrame(bytes(320), 8000, 1, 160,
                userdata={"received_at": 100 + (index + 1) * .02})
    class Output:
        def on(self, *args):
            pass
    class Provider:
        async def send_json(self, value):
            sent.append(base64.b64decode(value["user_audio_chunk"]))
    async def emit(*args, **kwargs):
        pass
    async def scenario():
        bridge = plivo.ManagedPlivo(SimpleNamespace(audio_input=incoming(), audio_output=Output()),
                                    Provider(), customer_name="Fixture", emit=emit)
        await bridge.input_audio()
        assert load_options[0]["sample_rate"] == 16000
        assert frames and all(frame.sample_rate == 16000 for frame in frames)
        assert [bytes(frame.data) for frame in frames] == sent
        assert bridge.clock.samples == 1600
        assert bridge.clock.frames[-1][2] == pytest.approx(100.18)
        await bridge.vad_stream.aclose()
    asyncio.run(scenario())
