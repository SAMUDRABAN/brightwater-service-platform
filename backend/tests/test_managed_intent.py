import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from semantic_fixture import bind
from sqlalchemy import select
from test_managed_phone import event, phone

from brightwater import models as m
from brightwater.config import settings
from brightwater.db import session
from brightwater.managed.intent import IntentEvidence, classify
from brightwater.managed.readback import compact, complete_readback
from brightwater.policy import Rejected, now


def proof(call, proposal, question, reply, decision='confirm'):
    return IntentEvidence(call.id, proposal.id, proposal.fingerprint, question, reply, decision)


@pytest.mark.parametrize('text,expected', [('PO four zero J T', 'po40jt'), ('P O four zero J T', 'po40jt'),
    ('twenty twenty-six', '2026'), ('twenty twenty-seven', '2027'), ('two thousand and twenty six', '2026'),
    ('ninety five pounds', '95pounds'), ('eight until twelve', '8until12')])
def test_actual_phone_numbers_are_not_added_together(text, expected):
    assert compact(text) == expected


def test_exact_twelfth_call_spoken_readback_and_wrong_year_postcode():
    proposal = SimpleNamespace(items=[{'property_id': 'ENGINEERING-P1', 'address': '18 Albert Road, Southsea, PO4 0JT',
        'service': 'service', 'day': '2026-11-16', 'period': 'MORNING'}], total_pence=9500)
    text = ('Just to confirm: eighteen Albert Road, Southsea, PO four zero J T, boiler service, on Monday '
        'the sixteenth of November twenty twenty-six in the morning, eight until twelve. The total is '
        'ninety-five pounds including VAT, payable to the engineer. Shall I book that for you?')
    assert complete_readback(text, proposal)
    for wrong in [text.replace('four zero', 'four one'), text.replace('twenty-six', 'twenty-seven'),
                  text.replace('ninety-five', 'one hundred and ninety-five'), text.replace('morning', 'afternoon')]:
        assert not complete_readback(wrong, proposal)


@pytest.mark.parametrize("reply", ["That works for me, pencil me in please.", "Uh, yeah, please do it."])
def test_semantic_paraphrase_commits_only_with_bound_fresh_original_evidence(reply):
    from datetime import timedelta
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        question = prepared['readback'].replace('PO4 0JT', 'PO four zero J T').replace('2026', 'twenty twenty-six').replace('18 Albert', 'eighteen Albert').replace('16th November', 'the sixteenth of November').replace('£95', 'ninety-five pounds')
        event(db, call, 'agent_utterance', now() - timedelta(seconds=2), source='plivo_elevenlabs_observer',
              text=question, playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', now() - timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text=reply, speech_timing_verified=True)
        conv.agent(question)
        conv.user(reply)
        original = proof(call, proposal, question, reply)
        conv.intent = replace(original, fingerprint='different')
        with pytest.raises(Rejected):
            conv.execute(db, 'confirm_booking', {'proposal_id': proposal.id}, 'wrong-proof')
        conv.intent = original
        result = conv.execute(db, 'confirm_booking', {'proposal_id': proposal.id}, 'good-proof')
        assert result['confirmed'] is True
        booking = db.get(m.Booking, result['booking_id'])
        windows = list(db.scalars(select(m.DiaryWindow).where(m.DiaryWindow.id.in_([i['window_id'] for i in proposal.items]))))
        before = sum(w.used_minutes for w in windows)
        # The next utterance requests cancellation: no guessed historic appointment.
        reply = "Actually, scrap that appointment, I don't need it now."
        event(db, call, 'user_utterance', now(), source='plivo_elevenlabs_observer', text=reply, speech_timing_verified=True)
        conv.user(reply)
        conv.intent = proof(call, proposal, question, reply, 'cancel')
        cancelled = conv.execute(db, 'cancel_arrangement', {'proposal_id': proposal.id}, 'cancel')
        assert cancelled['cancelled'] is True and booking.state == 'cancelled'
        assert sum(w.used_minutes for w in windows) == before - 60
        conv.execute(db, 'cancel_arrangement', {'proposal_id': proposal.id}, 'cancel-retry')
        assert sum(w.used_minutes for w in windows) == before - 60
        with pytest.raises(Rejected):
            conv.execute(db, 'confirm_booking', {'proposal_id': proposal.id}, 'cannot-resurrect')
        from brightwater.managed.gateway import closed_result
        call.state = 'finished'
        db.flush()
        assert closed_result(db, call.id, phone=True)['confirmed'] is False
    from fastapi.testclient import TestClient

    from brightwater.api import app
    response = TestClient(app).get('/v1/dashboard', headers={'Authorization': 'Bearer ' + settings().operator_token.get_secret_value()})
    assert response.status_code == 200
    assert all(row['booking_id'] != booking.id for row in response.json()['appointments'])


@pytest.mark.parametrize('decision', ['decline', 'change', 'cancel', 'question', 'unclear', 'unavailable'])
def test_semantic_non_authorisation_overrides_a_yes_and_never_books(decision):
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        conv.agent(prepared['readback'])
        conv.user('Yes')
        conv.intent = proof(call, proposal, prepared['readback'], 'Yes', decision)
        with pytest.raises(Rejected) as error:
            conv.execute(db, 'confirm_booking', {'proposal_id': proposal.id}, 'no-book')
        assert error.value.code == 'intent_' + decision
        assert not list(db.scalars(select(m.Booking)))


def test_classifier_uses_structured_server_inference_and_fails_closed(monkeypatch):
    monkeypatch.setattr(settings(), 'openai_api_key', SecretStr('synthetic-key'))
    proposal = SimpleNamespace(id='p', fingerprint='f', items=[{'address': '18 Albert Road, Southsea, PO4 0JT',
        'property_id': 'x', 'service': 'service', 'day': '2026-11-16', 'period': 'MORNING'}], total_pence=9500)
    def handle(request):
        payload = json.loads(request.content)
        assert payload['response_format']['json_schema']['strict'] is True
        assert payload['temperature'] == 0
        assert 'latest_customer_reply' in payload['messages'][-1]['content']
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"decision":"confirm"}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        value = classify('c', proposal, 'Readback?', 'Pencil me in', [], client=client)
    assert value.confirms('c', proposal, 'Pencil me in')
    assert not value.confirms('another-call', proposal, 'Pencil me in')
    assert not value.confirms('c', proposal, 'Actually cancel')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        assert classify('c', proposal, 'Readback?', 'Yes', [], client=client).decision == 'unavailable'


@pytest.mark.parametrize("failure", ["early", "missing_timing", "changed_reply"])
def test_semantic_confirm_never_overrides_original_carrier_evidence(failure):
    from datetime import timedelta
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        question = prepared['readback']
        reply = "Please get that arranged for me."
        playback_at = now() - timedelta(seconds=2)
        event(db, call, 'agent_utterance', playback_at, source='plivo_elevenlabs_observer',
              text=question, playback_completed=True, interrupted=False)
        event(db, call, 'user_utterance', playback_at + timedelta(seconds=-.1 if failure == 'early' else 1),
              source='plivo_elevenlabs_observer', text=reply if failure != 'changed_reply' else 'Actually cancel',
              speech_timing_verified=failure != 'missing_timing')
        conv.agent(question)
        conv.user(reply)
        conv.intent = proof(call, proposal, question, reply)
        with pytest.raises(Rejected):
            conv.execute(db, 'confirm_booking', {'proposal_id': proposal.id}, 'must-not-book')
        assert not list(db.scalars(select(m.Booking)))


def test_repeated_incomplete_readbacks_stop_instead_of_an_endless_yes_loop():
    from datetime import timedelta

    from brightwater.managed.engine import managed_error
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        question = prepared['readback'].replace(', PO4 0JT', '')
        for attempt in range(3):
            event(db, call, 'agent_utterance', now() - timedelta(seconds=2), source='plivo_elevenlabs_observer',
                  text=question, playback_completed=True, interrupted=False)
            event(db, call, 'user_utterance', now() - timedelta(seconds=1), source='plivo_elevenlabs_observer',
                  text='Yes, book it', speech_timing_verified=True)
            conv.agent(question)
            conv.user('Yes, book it')
            bind(db, conv, appointment='confirm')
            with pytest.raises(Rejected) as error:
                conv.execute(db, 'confirm_booking', {'proposal_id': prepared['proposal_id']}, 'attempt-' + str(attempt))
            if attempt >= 1:
                result = managed_error(error.value, agreement_present=True)
                assert result['error'] == 'booking_unavailable'
                assert result['retryable'] is False and result['customer_confirmation_needed'] is False
        assert not list(db.scalars(select(m.Booking)))
