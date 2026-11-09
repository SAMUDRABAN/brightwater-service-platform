import json
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
from pydantic import SecretStr
from semantic_fixture import bind, meaning
from sqlalchemy import select
from test_managed_candidate import start
from test_managed_phone import event, phone

from brightwater import models as m
from brightwater.config import settings
from brightwater.db import session
from brightwater.managed.semantic_runtime import apply_control, record_meaning
from brightwater.managed.understanding import (
    SpokenFacts,
    SpokenItem,
    interpret,
    semantic_readback,
    snapshot_digest,
)
from brightwater.policy import Rejected, now


@pytest.mark.parametrize('reply', ['Banerjee here, Samudra speaking.', 'You have reached the right person.', 'The person you asked for is me.'])
def test_identity_uses_bound_meaning_without_a_phrase_whitelist(reply):
    with session() as db, db.begin():
        call, conv = start(db)
        person = db.get(m.Customer, call.customer_id)
        person.name = 'Samudra Banerjee'
        conv.agent('May I check I have Samudra Banerjee on the line?')
        conv.user(reply)
        bind(db, conv, identity='self')
        assert conv.execute(db, 'confirm_identity', {}, 'identity')['verified'] is True


@pytest.mark.parametrize('failure', ['stale_reply', 'wrong_customer', 'wrong_source', 'no_notice', 'queued_question', 'new_prompt'])
def test_semantic_identity_does_not_override_carrier_or_privacy_guards(failure):
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        call.identity_verified = False
        # A fresh utterance after an actually played, naturally worded question.
        at = now() - timedelta(seconds=2)
        played = event(db, call, 'agent_utterance', at, source='plivo_elevenlabs_observer',
            text='Have I reached Helen Price herself?', playback_completed=True, interrupted=False)
        source = event(db, call, 'user_utterance', at + timedelta(seconds=1), source='plivo_elevenlabs_observer',
            text='Speaking, yes.', speech_timing_verified=True)
        conv.agent(played.payload['text'])
        conv.user(source.payload['text'])
        proof = bind(db, conv, identity='assent', identity_question=True)
        if failure == 'stale_reply':
            conv.understanding = replace(proof, reply='An earlier reply')
        elif failure == 'wrong_customer':
            conv.understanding = replace(proof, customer_name='Another customer')
        elif failure == 'wrong_source':
            source.payload = {**source.payload, 'source': 'model'}
        elif failure == 'no_notice':
            for row in db.scalars(select(m.CallEvent).where(m.CallEvent.kind == 'turn_state')):
                row.payload = {**row.payload, 'notice_delivered': False}
        elif failure == 'queued_question':
            played.payload = {**played.payload, 'playback_completed': False}
        elif failure == 'new_prompt':
            event(db, call, 'turn_state', at + timedelta(seconds=.5), source='managed_agent_prompt',
                  completed=False, native_event_id=999, revision=1)
        db.flush()
        try:
            result = conv.execute(db, 'confirm_identity', {}, 'fresh-identity')
            assert result['verified'] is False and 'account' not in result
        except Rejected:
            pass
        assert not call.identity_verified


@pytest.mark.parametrize('control', ['stop_calling', 'recording_refused', 'wrong_number', 'speaker_changed'])
def test_contextual_control_revokes_account_access_and_applies_once(control):
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        event(db, call, 'user_utterance', now(), source='plivo_elevenlabs_observer',
              text='A natural request interpreted in this test', speech_timing_verified=False)
        conv.user('A natural request interpreted in this test')
        proof = bind(db, conv, control=control)
        record_meaning(db, call, proof)
        assert apply_control(db, call, proof) is (control != 'speaker_changed')
        assert apply_control(db, call, proof) is (control != 'speaker_changed')
        assert call.identity_verified is False
        assert (call.state == 'finished') is (control != 'speaker_changed')
        keys = [e.provider_event_id for e in db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id))]
        assert len(keys) == len(set(keys))
        if control == 'stop_calling':
            assert list(db.scalars(select(m.Suppression)))


def test_contextual_callback_cannot_use_an_unplayed_offer_or_reverse_refusal():
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        at = now() - timedelta(seconds=2)
        event(db, call, 'agent_utterance', at, source='plivo_elevenlabs_observer',
              text='Would a call from the office tomorrow suit you?', playback_completed=False, interrupted=False)
        event(db, call, 'user_utterance', at + timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text='That would be handy', speech_timing_verified=True)
        conv.agent('Would a call from the office tomorrow suit you?')
        conv.user('That would be handy')
        bind(db, conv, followup='callback', followup_basis='contextual')
        with pytest.raises(Rejected):
            conv.execute(db, 'record_followup', {'kind': 'callback'}, 'no-request')
        assert not list(db.scalars(select(m.Followup)))
        assert not meaning(followup='callback', followup_basis='contextual').rescinds_callback_refusal
        evidence = conv.understanding
        assert not evidence.allows_followup('callback', previously_declined=True)
        assert replace(evidence, meaning=meaning(followup='callback', followup_basis='explicit',
                       rescinds_callback_refusal=True)).allows_followup('callback', previously_declined=True)


def example_snapshot():
    return {'call_id': 'offline', 'customer_name': 'Samudra Banerjee', 'reply': 'Samudra here',
        'question': 'Who is speaking?', 'source_id': 'u1', 'playback_id': 'a1', 'proposal_id': '',
        'fingerprint': '', 'history': [], 'completed_agent_speech': 'Who is speaking?',
        'callback_previously_declined': False, 'extract_readback': False}


def test_model_uses_strict_schema_and_does_not_receive_expected_proposal_facts(monkeypatch):
    monkeypatch.setattr(settings(), 'openai_api_key', SecretStr('synthetic-key'))
    data = example_snapshot()
    data.update(proposal_id='secret-proposal-id', fingerprint='secret-fingerprint')
    def respond(request):
        body = json.loads(request.content)
        assert body['response_format']['json_schema']['strict'] is True
        user = json.loads(body['messages'][-1]['content'])
        assert 'proposal_id' not in user and 'fingerprint' not in user
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(meaning(identity='self').model_dump(exclude={'readback'}))}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        proof = interpret(data, client=client)
    assert proof.matches('offline', 'Samudra Banerjee', 'Samudra here')
    assert not proof.matches('another', 'Samudra Banerjee', 'Samudra here')
    assert proof.digest == snapshot_digest(data)


@pytest.mark.parametrize('response', [httpx.Response(503), httpx.Response(200, json={'choices': [{'message': {'content': '{"identity":"self"}'}}]})])
def test_model_failure_is_unavailable_without_a_phrase_fallback(monkeypatch, response):
    monkeypatch.setattr(settings(), 'openai_api_key', SecretStr('synthetic-key'))
    data = example_snapshot() | {'reply': 'Yes, yes, book it'}
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        proof = interpret(data, client=client)
    assert proof.meaning is None and proof.appointment_evidence().decision == 'unavailable'


def test_singleflight_reuses_only_exact_context(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    import redis
    broker = redis.Redis.from_url(settings().redis_url.get_secret_value())
    monkeypatch.setattr(settings(), 'openai_api_key', SecretStr('synthetic-key'))
    data = example_snapshot() | {'call_id': m.uid()}
    requests = []
    def respond(request):
        requests.append(1)
        sleep(.05)
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(meaning(identity='self').model_dump(exclude={'readback'}))}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: interpret(data, client=client, redis=broker), range(8)))
        assert len(requests) == 1 and all(r.meaning.identity == 'self' for r in results)
        changed = interpret(data | {'reply': 'No, her son here'}, client=client, redis=broker)
        assert changed.digest != results[0].digest and len(requests) == 2
    broker.delete(*broker.scan_iter('managed:meaning:*' + snapshot_digest(data) + '*'))
    broker.delete('managed:meaning-budget:' + data['call_id'])


@pytest.mark.parametrize('failure', [None, 'wrong_postcode', 'wrong_price', 'missing_fact', 'forged_quote', 'different_proposal'])
def test_natural_readback_extracts_facts_but_cannot_rewrite_the_proposal(failure):
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        text = ('At 18 Albert Road, Southsea, PO4 0JT, the boiler service would be on 16 November 2026, '
                'arriving between 8am and noon. You would pay the engineer £95 altogether, VAT already included. '
                'Would you like me to reserve that visit?')
        event(db, call, 'agent_utterance', now() - timedelta(seconds=2), source='plivo_elevenlabs_observer',
              text=text, playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', now() - timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text='Go ahead', speech_timing_verified=True)
        conv.agent(text)
        conv.user('Go ahead')
        facts = SpokenFacts(unambiguous=True, items=[SpokenItem(address='18 Albert Road, Southsea', postcode='PO4 0JT',
            service='service', day='2026-11-16', period='MORNING', window_start=8, window_end=12,
            quote=text.split(' You would')[0])], total_pence=9500, vat_included=True, payment_to_engineer=True,
            asks_confirmation=True, price_quote='£95 altogether', vat_quote='VAT already included',
            payment_quote='pay the engineer', question_quote='Would you like me to reserve that visit?')
        if failure == 'wrong_postcode':
            facts.items[0].postcode = 'PO4 1JT'
        elif failure == 'wrong_price':
            facts.total_pence = 19500
        elif failure == 'missing_fact':
            facts.payment_to_engineer = False
        elif failure == 'forged_quote':
            facts.items[0].quote = 'These details were read correctly'
        proof = bind(db, conv, appointment='confirm', readback=facts)
        if failure == 'different_proposal':
            proof = replace(proof, fingerprint='other')
        assert semantic_readback(proof, proposal, text) is (failure is None)


def test_another_appointment_cannot_be_confirmed_or_cancelled_as_current():
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        conv.agent(prepared['readback'])
        conv.user('Cancel the other visit I booked last June, not this one.')
        event(db, call, 'user_utterance', now(), source='plivo_elevenlabs_observer',
            text=conv.latest_user()['text'], speech_timing_verified=True)
        proof = bind(db, conv, appointment='cancel', appointment_target='other')
        assert proof.appointment_evidence().decision == 'unclear'
        with pytest.raises(Rejected):
            conv.execute(db, 'cancel_arrangement', {'proposal_id': proposal.id}, 'wrong-appointment')
        assert proposal.state == 'prepared'


def test_unnamed_assent_cannot_skip_a_completed_identity_question():
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        call.identity_verified = False
        at = now() - timedelta(seconds=2)
        event(db, call, 'agent_utterance', at, source='plivo_elevenlabs_observer',
              text='Would you like to hear about our services?', playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', at + timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text='You have the right person', speech_timing_verified=True)
        conv.agent('Would you like to hear about our services?')
        conv.user('You have the right person')
        bind(db, conv, identity='self', identity_name_quote='', identity_question=False)
        assert conv.execute(db, 'confirm_identity', {}, 'not-named')['verified'] is False
        assert not call.identity_verified


def test_recording_refusal_backstop_ends_the_carrier_even_when_db_already_closed(monkeypatch):
    from brightwater.managed import semantic_runtime
    monkeypatch.setattr(settings(), 'managed_phone_enabled', True)
    stopped = []
    monkeypatch.setattr(semantic_runtime, 'stop_carrier', lambda call_id: stopped.append(call_id))
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        source = event(db, call, 'user_utterance', now(), source='plivo_elevenlabs_observer',
                       text='I do not consent to recording', speech_timing_verified=False)
        call_id, event_id = call.id, source.id
        assert call.state == 'finished'
    semantic_runtime.prefetch(call_id, event_id)
    assert stopped == [call_id]


def test_an_old_history_question_cannot_supply_current_identity_question_evidence():
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        call.identity_verified = False
        at = now() - timedelta(seconds=2)
        current = 'Would you like to hear about our services?'
        event(db, call, 'agent_utterance', at, source='plivo_elevenlabs_observer',
              text=current, playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', at + timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text='Yes please', speech_timing_verified=True)
        conv.agent(current)
        conv.user('Yes please')
        bind(db, conv, identity='assent', identity_question=True,
             identity_question_quote='Am I speaking with Helen Price?')
        assert conv.execute(db, 'confirm_identity', {}, 'wrong-question')['verified'] is False
        assert not call.identity_verified
