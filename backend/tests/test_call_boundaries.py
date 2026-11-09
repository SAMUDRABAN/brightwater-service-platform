"""Policy and real transport checks. Classifier accuracy is evaluated separately."""
import asyncio
import base64
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from semantic_fixture import bind
from sqlalchemy import func, select
from test_managed_phone import event, phone
from test_plivo_audio import ack, drained, frame, ready

from brightwater import models as m
from brightwater.db import session
from brightwater.managed.boundaries import terminal_reason
from brightwater.managed.closing import farewell
from brightwater.managed.plivo import ManagedPlivo
from brightwater.managed.semantic_runtime import apply_control, record_meaning
from brightwater.policy import now

WARNING = "I can help with Brightwater, but I'll end this call if the personal remarks continue."


def turn(db, call, conv, index, control, *, warning=True, completed=True, timing=True, followup='none'):
    at = now() - timedelta(seconds=4 - index)
    speech = WARNING if warning else 'Which date would you prefer?'
    event(db, call, 'agent_utterance', at - timedelta(seconds=.3), source='plivo_elevenlabs_observer',
          text=speech, playback_completed=completed, interrupted=not completed)
    event(db, call, 'user_utterance', at, source='plivo_elevenlabs_observer',
          text='Fictional caller turn ' + str(index), speech_timing_verified=timing)
    conv.agent(speech)
    conv.user('Fictional caller turn ' + str(index))
    proof = bind(db, conv, control=control, boundary_warning_quote=speech if warning else '', followup=followup)
    record_meaning(db, call, proof)
    return proof


@pytest.mark.parametrize('control,threshold', [('off_topic', 3), ('harassment', 2)])
def test_repeated_misuse_requires_warning_and_distinct_caller_turns(control, threshold):
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        for i in range(threshold):
            proof = turn(db, call, conv, i, control, warning=i > 0)
            record_meaning(db, call, proof)  # Retry cannot manufacture another turn.
            assert terminal_reason(db, call, proof) == (control if i == threshold - 1 else None)
        assert apply_control(db, call, proof)
        assert call.state == 'finished' and call.outcome != 'Booked'
        assert db.scalar(select(func.count()).select_from(m.Suppression)) == 0
        assert db.scalar(select(func.count()).select_from(m.Followup)) == 0
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
        assert db.scalar(select(func.count()).select_from(m.CallEvent).where(m.CallEvent.kind == 'turn_state',
            m.CallEvent.payload['source'].as_string() == 'boundary_terminal_requested')) == 1


@pytest.mark.parametrize('reason', ['automated_menu', 'voicemail'])
def test_unambiguous_automation_stops_without_identity_or_warning(reason):
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        call.identity_verified = False
        proof = turn(db, call, conv, 0, reason, warning=False)
        assert terminal_reason(db, call, proof) == reason
        result = conv.execute(db, 'finish_conversation', {}, 'automation')
        assert result['stopped'] and result['boundary_reason'] == reason
        assert call.state == 'finished'
        assert not db.scalar(select(m.Suppression))


@pytest.mark.parametrize('variation', ['no_warning', 'interrupted_warning', 'invented_warning', 'unverified_speech',
    'stale', 'newer_reply', 'return_to_service', 'unknown_turn', 'gas_emergency', 'co_alarm', 'complaint', 'urgent',
    'callback', 'lead', 'decline_callback', 'appointment_change'])
def test_uncertainty_and_real_enquiries_never_become_misuse_hangups(variation):
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        turn(db, call, conv, 0, 'harassment', warning=False)
        if variation == 'return_to_service':
            turn(db, call, conv, 1, 'none')
        if variation == 'unknown_turn':
            event(db, call, 'user_utterance', now() - timedelta(seconds=3),
                source='plivo_elevenlabs_observer', text='Unclassified reply', speech_timing_verified=True)
        proof = turn(db, call, conv, 2, 'harassment', warning=variation != 'no_warning',
            completed=variation != 'interrupted_warning', timing=variation != 'unverified_speech',
            followup=variation if variation in {'gas_emergency', 'co_alarm', 'complaint', 'urgent', 'callback', 'lead', 'decline_callback'} else 'none')
        if variation == 'appointment_change':
            proof = replace(proof, meaning=proof.meaning.model_copy(update={'appointment': 'change', 'appointment_target': 'current'}))
        if variation == 'invented_warning':
            # Remove grounded warning and re-record a fabricated quote as a new snapshot.
            row = db.scalar(select(m.CallEvent).where(m.CallEvent.kind == 'semantic_turn',
                m.CallEvent.provider_event_id == 'semantic-turn:' + proof.digest))
            db.delete(row)
            db.flush()
            proof = replace(proof, meaning=proof.meaning.model_copy(update={'boundary_warning_quote': 'A fabricated warning that was never played aloud'}))
            record_meaning(db, call, proof)
        if variation == 'stale':
            db.get(m.CallEvent, proof.source_id).occurred_at = now() - timedelta(seconds=40)
            db.flush()
        if variation == 'newer_reply':
            event(db, call, 'user_utterance', now(), source='plivo_elevenlabs_observer', text='I need Tuesday please', speech_timing_verified=True)
        assert terminal_reason(db, call, proof) is None
        assert not apply_control(db, call, proof)
        assert call.state == 'in_progress'


def test_first_misuse_cannot_use_finish_tool_to_skip_warning():
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        turn(db, call, conv, 0, 'harassment', warning=False)
        result = conv.execute(db, 'finish_conversation', {}, 'premature-finish')
        assert result['finished'] is False
        assert not conv.closed and call.state == 'in_progress'


def test_saved_booking_survives_conduct_ending():
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        at = now() - timedelta(seconds=5)
        db.get(m.Proposal, prepared['proposal_id']).created_at = at - timedelta(seconds=1)
        event(db, call, 'agent_utterance', at, source='plivo_elevenlabs_observer',
              text=prepared['readback'], playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', at + timedelta(seconds=.5), source='plivo_elevenlabs_observer',
              text='Please reserve that', speech_timing_verified=True)
        conv.agent(prepared['readback'])
        conv.user('Please reserve that')
        bind(db, conv, appointment='confirm')
        result = conv.execute(db, 'confirm_booking', {'proposal_id': prepared['proposal_id']}, 'save')
        assert result['confirmed']
        booking = db.scalar(select(m.Booking))
        saved = (booking.id, booking.state, booking.total_pence)
        turn(db, call, conv, 1, 'harassment', warning=False)
        proof = turn(db, call, conv, 2, 'harassment')
        assert apply_control(db, call, proof)
        assert (booking.id, booking.state, booking.total_pence) == saved
        assert call.outcome == 'Booked'


@pytest.mark.parametrize('provider_fails', [False, True])
def test_graceful_boundary_stops_provider_drains_input_and_retains_playout_proof(provider_fails):
    async def scenario():
        transport, ws = await ready()
        order, audits = [], []
        class Provider:
            async def send_json(self, value):
                pass
            async def __aiter__(self):
                await asyncio.Event().wait()
                yield {}
            async def aclose(self):
                order.append('provider_closed')
        async def emit(kind, payload, **kwargs):
            audits.append((kind, payload))
        async def goodbye():
            assert order == ['provider_closed']
            if provider_fails:
                raise httpx.TimeoutException('Synthetic provider timeout')
            # Exercise actual carrier clear/playback receipts, not a fake completion.
            await drained(transport)
            await transport.handle_message({'event': 'clearedAudio', 'sequenceNumber': 2, 'streamId': 'stream'})
            for sequence in range(3, 153):
                await transport.handle_message({'event': 'media', 'sequenceNumber': sequence, 'streamId': 'stream',
                    'media': {'track': 'inbound', 'payload': base64.b64encode(b'\xff' * 160).decode()}})
                await asyncio.sleep(.001)
            assert transport._input.qsize() < 10
            assert transport.failure_reason is None
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.flush()
            await drained(transport)
            for item in list(ws.sent):
                if item.get('event') == 'checkpoint':
                    await transport.handle_message(ack(item['name'], 200))
            result = await transport.audio_output.wait_for_playout()
            order.append('goodbye_played')
            return not result.interrupted
        bridge = ManagedPlivo(transport, Provider(), customer_name='Fixture', emit=emit, farewell=goodbye)
        bridge.boundary_requested.set()
        try:
            await asyncio.wait_for(bridge.run(), 3)
            assert order == (['provider_closed'] if provider_fails else ['provider_closed', 'goodbye_played'])
            assert ('turn_state', {'source': 'boundary_closing', 'playback_completed': not provider_fails}) in audits
            assert not any(k == 'agent_utterance' for k, _ in audits), 'Closing is not business consent evidence'
        finally:
            await transport.aclose()
    asyncio.run(scenario())


def test_farewell_uses_current_owned_voice_and_bounds_audio_without_business_evidence():
    async def scenario():
        requested = []
        def response(request):
            requested.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'conversation_config': {'tts': {'voice_id': 'selectedValory', 'model_id': 'eleven_v4_turbo'}}})
            return httpx.Response(200, content=bytes(6400))
        class Output:
            def __init__(self): self.samples = 0
            async def capture_frame(self, frame): self.samples += frame.samples_per_channel
            def flush(self): pass
            async def wait_for_playout(self): return SimpleNamespace(interrupted=False)
        output = Output()
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
            assert await farewell(http, 'synthetic', 'agent_owned', output)
        assert output.samples == 1600
        assert str(requested[1].url).startswith('https://api.elevenlabs.io/v1/text-to-speech/selectedValory/stream')
        assert b'eleven_v4_turbo' in requested[1].content
    asyncio.run(scenario())
