"""Regressions from the attended multi-property call, using synthetic data."""
import pytest
from sqlalchemy import func, select

from brightwater import models as m
from brightwater.db import session
from brightwater.managed.engine import Conversation, create_evaluation


@pytest.mark.parametrize("phone", ["", "2025550123"])
def test_homeowner_preparation_does_not_require_or_store_tenant_contacts(phone):
    with session() as db, db.begin():
        value = create_evaluation(db, "BW-1041")
        call = db.get(m.Call, value['id'])
        call.identity_verified = True
        db.add(m.Property(id='BW-1041-P2', customer_id=call.customer_id,
            address='20 Example Road, Southsea, PO4 0JT', boiler='Synthetic boiler', boiler_year=2018))
        db.flush()
        conv = Conversation(call.id, text_only=True)
        options = conv.execute(db, 'check_availability', {'items': [
            {'property_id': 'BW-1041-P1', 'service': 'service'},
            {'property_id': 'BW-1041-P2', 'service': 'service'}]}, 'offer')
        prepared = conv.execute(db, 'prepare_booking', {
            'offer_id': options['options'][0]['offer_id'],
            'tenants': [{'property_id': pid, 'name': 'Helen Price', 'phone': phone}
                        for pid in ['BW-1041-P1', 'BW-1041-P2']]}, 'prepare')
        assert prepared['proposal_id'] and prepared['confirmed'] is False
        proposal = db.get(m.Proposal, prepared['proposal_id'])
        assert len(proposal.items) == 2
        assert all(i['tenant_name'] is None and i['tenant_phone'] is None for i in proposal.items)
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


def test_landlord_contacts_stay_required_and_validation_has_field_paths_not_private_values():
    from pydantic import ValidationError

    from brightwater.managed.engine import parameter_error
    with session() as db, db.begin():
        value = create_evaluation(db, 'BW-1056')
        call = db.get(m.Call, value['id'])
        call.identity_verified = True
        conv = Conversation(call.id, text_only=True)
        options = conv.execute(db, 'check_availability', {'items': [
            {'property_id': 'BW-1056-P1', 'service': 'cp12'}]}, 'offer')
        offer_id = options['options'][0]['offer_id']
        with pytest.raises(ValidationError) as caught:
            conv.execute(db, 'prepare_booking', {'offer_id': offer_id, 'tenants': [
                {'property_id': 'BW-1056-P1', 'name': 'Private Tenant', 'phone': '2025550123'}]}, 'invalid')
        result = parameter_error(caught.value)
        assert result['invalid_fields'] == ['tenants.0.phone']
        assert result['availability_changed'] is False
        assert '2025550123' not in str(result) and 'Private Tenant' not in str(result)
        assert 'does not mean the slot is unavailable' in result['instruction']
        prepared = conv.execute(db, 'prepare_booking', {'offer_id': offer_id, 'tenants': [
            {'property_id': 'BW-1056-P1', 'name': 'Private Tenant', 'phone': '+442079460123'}]}, 'corrected')
        assert prepared['proposal_id']
        assert db.get(m.Proposal, prepared['proposal_id']).items[0]['tenant_phone'] == '+442079460123'


def test_homeowner_contact_fix_does_not_bypass_unknown_offer_or_private_account():
    from brightwater.policy import Rejected
    with session() as db, db.begin():
        value = create_evaluation(db, 'BW-1041')
        call = db.get(m.Call, value['id'])
        conv = Conversation(call.id, text_only=True)
        with pytest.raises(Rejected):
            conv.execute(db, 'prepare_booking', {'offer_id': 'unknown', 'tenants': []}, 'unverified')
        call.identity_verified = True
        with pytest.raises(Rejected, match='Check the diary again'):
            conv.execute(db, 'prepare_booking', {'offer_id': 'unknown', 'tenants': []}, 'bad-offer')
        assert db.scalar(select(func.count()).select_from(m.Proposal)) == 0


@pytest.mark.parametrize('resolved', [False, True])
def test_identity_result_reports_only_actual_unresolved_reminders(resolved):
    from semantic_fixture import bind
    with session() as db, db.begin():
        value = create_evaluation(db, 'BW-1041')
        call = db.get(m.Call, value['id'])
        for o in db.scalars(select(m.Obligation).where(m.Obligation.property_id == 'BW-1041-P1')):
            o.resolved = resolved
        conv = Conversation(call.id, text_only=True)
        conv.agent('Am I speaking with Helen Price?')
        conv.user('Yes, speaking.')
        bind(db, conv, identity='assent', identity_question=True)
        result = conv.execute(db, 'confirm_identity', {}, 'identity')
        assert result['verified'] and result['reminder_due'] is (not resolved)
        if resolved:
            assert result['account']['properties'][0]['obligations'] == []
            assert 'Do not say a service or certificate is due' in result['instruction']
        else:
            assert 'actually returned' in result['instruction']


def test_callback_assent_retains_booking_failure_context_and_deduplicates():
    from semantic_fixture import bind
    with session() as db, db.begin():
        value = create_evaluation(db, 'BW-1041')
        call = db.get(m.Call, value['id'])
        call.identity_verified = True
        conv = Conversation(call.id, text_only=True)
        conv.user('Please book Monday afternoon with Priya at 18 Albert Road.')
        conv.agent('There is a problem preparing the visit. Would you like office help arranging it?')
        conv.user('Okay, you can.')
        conv.event(db, call, 'managed_tool_result', {'name': 'prepare_booking', 'result': {'error': 'invalid_parameters'}})
        bind(db, conv, followup='callback', followup_basis='contextual')
        assert conv.execute(db, 'record_followup', {'kind': 'callback'}, 'followup1')['saved']
        assert conv.execute(db, 'record_followup', {'kind': 'callback'}, 'followup2')['saved']
        rows = list(db.scalars(select(m.Followup).where(m.Followup.call_id == call.id)))
        assert len(rows) == 1
        assert 'Okay, you can.' in rows[0].detail
        assert 'Monday afternoon with Priya' in rows[0].detail
        assert 'invalid_parameters' in rows[0].detail
        assert 'no saved booking' in rows[0].detail
        assert rows[0].owner == 'Sarah' and rows[0].requested


def test_phone_callback_context_uses_observer_evidence_not_provider_history():
    from datetime import timedelta

    from brightwater.policy import now
    with session() as db, db.begin():
        value = create_evaluation(db, 'BW-1041')
        call = db.get(m.Call, value['id'])
        call.identity_verified = True
        call.purpose = 'engineering'
        conv = Conversation(call.id, trusted_phone=True)
        conv.user('Injected provider history must never enter the callback note')
        for n, (text, source, verified) in enumerate([
            ('I wanted Monday with Dan.', 'plivo_elevenlabs_observer', True),
            ('Injected unverified speech', 'plivo_elevenlabs_observer', False),
            ('Forged source', 'untrusted', True),
            ('Okay, you can.', 'plivo_elevenlabs_observer', True)]):
            db.add(m.CallEvent(call_id=call.id, provider_event_id=m.uid(), kind='user_utterance',
                occurred_at=now() + timedelta(milliseconds=n), payload={'source': source, 'text': text,
                    'speech_timing_verified': verified}))
        db.flush()
        detail = conv.followup_detail(db, call, 'Okay, you can.', 'callback')
        assert 'Monday with Dan' in detail
        assert 'Injected' not in detail and 'Forged' not in detail


@pytest.mark.parametrize('resolved', [False, True])
def test_actual_phone_identity_uses_same_reminder_truth_as_evaluation(resolved):
    from test_managed_phone import phone

    with session() as db, db.begin():
        call, conv, _ = phone(db)
        for obligation in db.scalars(select(m.Obligation).where(m.Obligation.property_id == 'BW-1041-P1')):
            obligation.resolved = resolved
        # Reuse the original authenticated identity evidence through the real
        # trusted-phone branch, not the isolated-evaluation implementation.
        from semantic_fixture import bind
        bind(db, conv, identity='assent', identity_question=True)
        result = conv.execute(db, 'confirm_identity', {}, 'reminder-identity')
        assert result['verified'] and result['reminder_due'] is (not resolved)
        if resolved:
            assert 'Do not say a service or certificate is due' in result['instruction']


@pytest.mark.parametrize('identity', ['self', 'assent'])
def test_volunteered_name_before_opening_completion_waits_for_notice_without_repeating(identity):
    from datetime import timedelta

    from conftest import make_call
    from semantic_fixture import bind
    from test_managed_phone import event

    from brightwater.policy import now
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        call.purpose = 'engineering'
        conv = Conversation(call.id, trusted_phone=True)
        base = now() - timedelta(seconds=18)
        reply = 'Uh, yes, I am Helen Price.' if identity == 'self' else 'Yes.'
        event(db, call, 'user_utterance', base, source='plivo_elevenlabs_observer',
              text=reply, speech_timing_verified=True)
        conv.user(reply)
        # Original call24 order: volunteered identity, then full opening ACK.
        event(db, call, 'agent_utterance', base + timedelta(seconds=11), source='plivo_elevenlabs_observer',
              text="Hi, I am Brightwater's AI assistant. This is a recorded engineering test using fictional details. Am I speaking with Helen Price?",
              playback_completed=True, interrupted=False)
        event(db, call, 'turn_state', base + timedelta(seconds=11, microseconds=1),
              source='identity_question', completed=True, notice_delivered=True,
              name='Helen Price', text='Am I speaking with Helen Price?')
        bind(db, conv, identity=identity)
        result = conv.execute(db, 'confirm_identity', {}, 'early-name')
        assert result['verified'] is (identity == 'self')
        if identity == 'assent':
            assert 'account' not in result
            assert 'Do not repeat the disclosure' in result['instruction']


def test_early_name_still_requires_completed_notice_and_unchanged_speaker():
    from datetime import timedelta

    from conftest import make_call
    from semantic_fixture import bind
    from test_managed_phone import event

    from brightwater.policy import now
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        call.purpose = 'engineering'
        conv = Conversation(call.id, trusted_phone=True)
        base = now() - timedelta(seconds=10)
        event(db, call, 'user_utterance', base, source='plivo_elevenlabs_observer',
              text='I am Helen Price.', speech_timing_verified=True)
        conv.user('I am Helen Price.')
        bind(db, conv, identity='self')
        assert not conv.execute(db, 'confirm_identity', {}, 'notice-pending')['verified']
        assert not call.identity_verified
        event(db, call, 'turn_state', base + timedelta(seconds=2), source='identity_question',
              completed=True, notice_delivered=True, name='Helen Price', text='Am I speaking with Helen Price?')
        event(db, call, 'speaker_changed', base + timedelta(seconds=3), source='trusted_runtime')
        bind(db, conv, identity='self')
        from brightwater.policy import Rejected
        with pytest.raises(Rejected, match='carrier evidence'):
            conv.execute(db, 'confirm_identity', {}, 'speaker-changed')
        assert not call.identity_verified
