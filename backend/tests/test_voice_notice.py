import asyncio
from types import SimpleNamespace

import pytest


def test_identity_returns_account_only_after_backend_verification():
    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        order = []
        agent = BrightwaterAgent(None, 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        async def final():
            return SimpleNamespace(event_id='fresh-caller')
        async def event(kind, payload):
            order.append('verified')
        async def request(method, path):
            assert order == ['verified'] and path == '/runtime/account'
            order.append('account')
            return {'name': 'Samudra', 'properties': []}
        agent.turns.final, agent.event, agent.request = final, event, request
        result = await agent.confirm_customer()
        assert result['identity_confirmed'] is True and result['account']['name'] == 'Samudra'
        assert order == ['verified', 'account']
    asyncio.run(run())


def test_latency_samples_exclude_content_and_invalid_values():
    from brightwater.plivo_gateway import latency_sample
    sample = latency_sample(SimpleNamespace(type='llm_metrics', ttft=.25, duration=1.,
        ttfb=float('nan'), transcription_delay=-1, api_key='private', transcript='private'))
    assert sample['ttft'] == .25 and sample['duration'] == 1.
    assert not {'ttfb', 'transcription_delay', 'api_key', 'transcript'} & sample.keys()
    assert latency_sample(SimpleNamespace(type='vad_metrics')) is None


def test_latency_telemetry_failure_does_not_fail_voice():
    from brightwater.plivo_gateway import record_latency
    class Broken:
        def pipeline(self):
            raise RuntimeError('unavailable')
    asyncio.run(record_latency(Broken(), 'synthetic', SimpleNamespace(type='llm_metrics', ttft=.2)))


@pytest.mark.parametrize('text', ['Yeah, please do it.', 'Yeah, yeah, do it.', 'Um, yes, book it.', 'Yep.'])
def test_natural_booking_affirmations(text):
    from brightwater.policy import explicit_yes
    assert explicit_yes(text)


@pytest.mark.parametrize('text', ['Yeah, but not that date.', 'I said yes before, not now.', 'She said yes.', 'Yes, you are.'])
def test_booking_affirmations_do_not_extract_assent_from_other_intents(text):
    from brightwater.policy import explicit_yes
    assert not explicit_yes(text)


def test_booking_confirmation_failure_is_not_reported_as_slot_failure():
    import httpx

    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        agent = BrightwaterAgent(None, 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        async def final():
            return SimpleNamespace(event_id='latest')
        async def request(*args, **kwargs):
            response = httpx.Response(400, json={'error': 'confirmation_required'},
                request=httpx.Request('POST', 'https://api.example.test/runtime/bookings/commit'))
            response.raise_for_status()
        agent.turns.final = final
        agent.turns.accepts = lambda *args: True
        agent.request = request
        result = await agent.commit_booking('proposal')
        assert result['status'] == 'confirmation_required'
        assert result['booking_created'] is False
    asyncio.run(run())


def test_finish_waits_for_preface_playout_and_context_is_not_an_llm_argument():
    from livekit.agents.llm.utils import build_strict_openai_schema

    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        order = []
        class Context:
            async def wait_for_playout(self):
                order.append('playout')
        class Room:
            async def disconnect(self):
                order.append('hangup')
        async def request(*args, **kwargs):
            order.append('finish')
        agent = BrightwaterAgent(SimpleNamespace(room=Room()), 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        agent.request = request
        schema = next(build_strict_openai_schema(t) for t in agent.tools if t.info.name == 'finish_call')
        assert set(schema['function']['parameters']['properties']) == {'summary'}
        await agent.finish_call('Test call ended.', Context())
        assert order == ['playout', 'finish', 'hangup']
    asyncio.run(run())


@pytest.mark.parametrize("interrupted", [True, False])
def test_identity_is_not_asserted_until_notice_completes_and_identity_is_reasked(monkeypatch, interrupted):
    pytest.importorskip("livekit.agents")
    from brightwater.voice_agent import BrightwaterAgent

    class Speech:
        async def wait_for_playout(self):
            pass

    played = Speech()
    played.interrupted = interrupted
    spoken = []
    calls = []

    def say(text, **kwargs):
        spoken.append(text)
        return played

    monkeypatch.setattr(BrightwaterAgent, "session", property(lambda _: SimpleNamespace(say=say)))

    async def run():
        agent = BrightwaterAgent(None, "not-real", "not-real", None,
            cfg=SimpleNamespace(recording_notice="This engineering call is recorded."), notice_required=True)

        async def event(*args, **kwargs):
            calls.append(args)
            return "not-real"

        agent.event = event
        response = await agent.confirm_customer()
        assert response["identity_confirmed"] is False
        assert not calls
        assert spoken == ["This engineering call is recorded."]
        assert agent.notice_delivered is (not interrupted)
    asyncio.run(run())


@pytest.mark.parametrize('interrupted', [False, True])
def test_identity_question_is_eligible_only_after_completed_playback(monkeypatch, interrupted):
    from brightwater.voice_agent import BrightwaterAgent
    completed, spoken, events = [], [], []

    class Speech:
        async def wait_for_playout(self):
            completed.append(True)

    speech = Speech()
    speech.interrupted = interrupted
    def say(text, **kwargs):
        spoken.append(text)
        return speech
    monkeypatch.setattr(BrightwaterAgent, 'session', property(lambda _: SimpleNamespace(say=say)))

    async def run():
        agent = BrightwaterAgent(None, 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        async def event(kind, payload):
            if payload['completed']:
                assert completed
            events.append((kind, payload))
        agent.event = event
        reply = await agent.ask_customer_identity()
        assert reply['question_completed'] is (not interrupted)
        assert spoken == ['Am I speaking with Samudra?']
        assert len(events) == 2
        assert events[0][1]['name'] == 'Samudra' and events[0][1]['completed'] is False
        assert events[-1][1]['completed'] is (not interrupted)
        duplicate = await agent.ask_customer_identity()
        assert duplicate['status'] == 'awaiting_reply' and len(spoken) == 1
        agent.turns.epoch += 1
        await agent.ask_customer_identity()
        agent.turns.epoch += 1
        third = await agent.ask_customer_identity()
        if interrupted:
            assert third['question_completed'] is False and len(spoken) == 3
            agent.turns.epoch += 1
            exhausted = await agent.ask_customer_identity()
            assert exhausted['status'] == 'needs_office_help' and len(spoken) == 3
        else:
            assert third['status'] == 'needs_office_help' and len(spoken) == 2
    asyncio.run(run())


@pytest.mark.parametrize('case', [
    'valid', 'valid_yeah', 'valid_hesitation', 'missing_question', 'interrupted_question', 'wrong_name', 'early_yes',
    'stale_yes', 'unverified_timing', 'different_question', 'speaker_handoff',
    'interruption', 'superseded_yes', 'notice_missing',
    'new_incomplete_question', 'interrupted_spoken_question', 'expired_question', 'proxy_yes',
])
def test_backend_yes_requires_current_completed_named_question(case):
    from datetime import timedelta
    from uuid import uuid4

    from conftest import make_call

    from brightwater import models as m
    from brightwater import services as svc
    from brightwater.db import session
    from brightwater.policy import Rejected, now
    from brightwater.schemas import EventInput

    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        name = db.get(m.Customer, call.customer_id).name
        base = now() - timedelta(seconds=90 if case in {'stale_yes', 'expired_question'} else 10)
        question = 'Am I speaking with ' + name + '?'
        def insert(kind, at, payload):
            event = m.CallEvent(call_id=call.id, provider_event_id=str(uuid4()),
                kind=kind, occurred_at=at, payload=payload)
            db.add(event)
            db.flush()
            return event
        if case != 'missing_question':
            insert('turn_state', base, {'source': 'identity_question', 'name': name if case != 'wrong_name' else 'Another Person',
                'text': question, 'completed': case != 'interrupted_question', 'notice_delivered': case != 'notice_missing'})
        if case in {'different_question', 'speaker_handoff', 'interruption'}:
            kind = {'different_question': 'agent_utterance', 'speaker_handoff': 'speaker_changed', 'interruption': 'interruption'}[case]
            insert(kind, base + timedelta(milliseconds=500), {'text': 'Would you like a callback?'})
        if case == 'new_incomplete_question':
            insert('turn_state', base + timedelta(milliseconds=500), {'source': 'identity_question',
                'name': name, 'text': question, 'completed': False, 'notice_delivered': True})
        if case == 'interrupted_spoken_question':
            insert('agent_utterance', base + timedelta(milliseconds=500), {'text': question, 'interrupted': True})
        yes_at = now() - timedelta(seconds=1) if case == 'expired_question' else base + timedelta(seconds=-1 if case == 'early_yes' else 1)
        reply = {'proxy_yes': 'Yes, I am her son', 'valid_yeah': 'Yeah, yeah, you are.', 'valid_hesitation': 'Uh, yes, you are.'}.get(case, 'Yes')
        yes = insert('user_utterance', yes_at,
            {'text': reply, 'speech_timing_verified': case != 'unverified_timing'})
        if case == 'superseded_yes':
            insert('user_utterance', base + timedelta(seconds=2), {'text': 'Actually no'})
        assertion = EventInput(provider_event_id=str(uuid4()), kind='identity_assertion', occurred_at=now(),
            payload={'utterance_event_id': yes.id})
        if case.startswith('valid'):
            svc.record_event(db, call.id, assertion)
            assert call.identity_verified is True
        else:
            with pytest.raises(Rejected), db.begin_nested():
                svc.record_event(db, call.id, assertion)
            assert call.identity_verified is False


@pytest.mark.parametrize('spoken', [
    'I am Janet Williams.', 'My name is Janet Williams.',
    'Yes, this is Janet Williams.', 'Yes, Janet Williams speaking.',
    "Yes, I'm Janet Williams.", 'Yes, I am Janet Williams.',
])
def test_natural_direct_self_introductions_are_accepted(spoken):
    from brightwater.policy import self_identifies
    assert self_identifies(spoken, 'Janet Williams')


@pytest.mark.parametrize('spoken', [
    "I am Janet Williams's daughter.", 'My name is Mark, Janet Williams is my mother.',
    'I am not Janet Williams.', 'Yes', 'Janet Williams is not here.',
])
def test_natural_introductions_do_not_accept_proxy_negation_or_generic_yes(spoken):
    from brightwater.policy import self_identifies
    assert not self_identifies(spoken, 'Janet Williams')


@pytest.mark.parametrize('spoken', [
    'Yeah, yeah, you are.', 'Uh, yes, you are.', 'Yeah, I am.', 'Yep.',
    "Um, that's right.", "Yes, that's correct.", 'Yes, you are.',
])
def test_question_bound_identity_accepts_natural_hesitations(spoken):
    from brightwater.policy import identity_affirmative
    assert identity_affirmative(spoken)


@pytest.mark.parametrize('spoken', [
    'Uh, no, you are not.', 'Yeah, my mother is Janet.', 'I heard her say yes.',
    'Yes, not me.', 'Yes, but this is her daughter.', 'She said yes.',
])
def test_question_bound_identity_rejects_negated_proxy_or_quoted_affirmations(spoken):
    from brightwater.policy import identity_affirmative
    assert not identity_affirmative(spoken)


def test_recipient_is_seeded_and_failed_identity_cannot_loop_indefinitely():
    import httpx

    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        agent = BrightwaterAgent(None, 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        assert 'Recipient name (data): "Samudra"' in agent.instructions
        assert 'Never say "the named customer"' in agent.instructions
        posted = []
        current = {'id': 'current-user-event'}

        async def final():
            return SimpleNamespace(event_id=current['id'])

        async def event(kind, payload):
            posted.append((kind, payload))
            response = httpx.Response(403, json={'error': 'identity_uncertain'},
                request=httpx.Request('POST', 'https://api.example.test/events'))
            response.raise_for_status()

        agent.turns.final = final
        agent.event = event
        first = await agent.confirm_customer()
        assert first['identity_confirmed'] is False
        assert first['question'] == 'Could you tell me your name, please?'
        duplicate = await agent.confirm_customer()
        assert duplicate['status'] == 'awaiting_reply' and len(posted) == 1
        current['id'] = 'second-user-event'
        second = await agent.confirm_customer()
        assert second['status'] == 'needs_office_help'
        current['id'] = 'third-user-event'
        third = await agent.confirm_customer()
        assert third['status'] == 'needs_office_help'
        assert len(posted) == 2
    asyncio.run(run())


@pytest.mark.parametrize('evidence', ['connected', 'signed_status', 'gateway_failure', 'reconciled', 'unanswered', 'untrusted_claim'])
def test_answered_calls_are_not_classified_as_no_answer(evidence):
    from uuid import uuid4

    from conftest import make_call
    from sqlalchemy import select

    from brightwater import models as m
    from brightwater import services as svc
    from brightwater.db import session
    from brightwater.policy import now

    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        sources = {'signed_status': 'signed_plivo_status', 'gateway_failure': 'voice_gateway_failure',
            'reconciled': 'authenticated_carrier_reconciliation', 'untrusted_claim': 'unknown_source'}
        if evidence != 'unanswered':
            db.add(m.CallEvent(call_id=call.id, provider_event_id=str(uuid4()),
                kind='connected' if evidence == 'connected' else 'turn_state', occurred_at=now(),
                payload={'source': sources.get(evidence), 'carrier_answered': True}))
            db.flush()
        svc.finalise(db, call, 'Engineering call ended without a booking.')
        svc.finalise(db, call, 'Engineering call ended without a booking.')
        answered = evidence not in {'unanswered', 'untrusted_claim'}
        assert call.outcome is None if answered else call.outcome == 'No answer'
        reviews = db.scalars(select(m.Followup).where(m.Followup.call_id == call.id, m.Followup.kind == 'internal_review')).all()
        assert len(reviews) == (1 if answered else 0)


@pytest.mark.parametrize('has_evidence', [True, False])
def test_office_followup_acknowledgement_is_not_a_live_transfer(has_evidence):
    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        agent = BrightwaterAgent(None, 'synthetic', 'synthetic', None, cfg=SimpleNamespace())
        events = []
        async def final(**kwargs):
            return SimpleNamespace(event_id='caller-request') if has_evidence else None
        async def event(kind, payload):
            events.append((kind, payload))
            return 'audit-event'
        agent.turns.final, agent.event = final, event
        result = await agent.escalate('callback', 'Caller agreed to an office callback.')
        assert result['recorded'] is has_evidence
        if has_evidence:
            assert result['live_transfer_available'] is False
            assert result['delivery'] == 'office_followup_recorded'
            assert result['event_id'] == 'audit-event' and len(events) == 1
        else:
            assert not events
    asyncio.run(run())
