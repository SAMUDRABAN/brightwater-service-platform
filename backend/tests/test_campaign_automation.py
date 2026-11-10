from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import make_call
from pydantic import SecretStr
from semantic_fixture import bind
from sqlalchemy import func, select
from test_managed_phone import phone

from brightwater import models as m
from brightwater import services as svc
from brightwater.campaign import configuration_issues, due_customers, enqueue_due, voicemail_result
from brightwater.config import settings
from brightwater.db import session
from brightwater.managed.semantic_runtime import record_meaning
from brightwater.policy import now

AT = datetime(2026, 11, 5, 12, tzinfo=UTC)


def test_due_selection_prioritises_landlords_deduplicates_properties_and_excludes_old_or_late_dates():
    with session() as db, db.begin():
        for obligation in db.scalars(select(m.Obligation)):
            obligation.due_date = date(2026, 12, 20)
        # Two due properties still generate only one customer.
        for pid in ['BW-1056-P1', 'BW-1056-P2']:
            db.scalar(select(m.Obligation).where(m.Obligation.property_id == pid)).due_date = date(2026, 11, 25)
        db.scalar(select(m.Obligation).where(m.Obligation.property_id == 'BW-1041-P1')).due_date = date(2026, 11, 6)
        db.scalar(select(m.Obligation).where(m.Obligation.property_id == 'BW-1120-P1')).due_date = date(2026, 11, 4)
        db.flush()
        rows = due_customers(db, AT)
        assert [c.id for c, _ in rows] == ['BW-1056', 'BW-1041']


def test_scheduler_is_idempotent_and_honours_approval_preferences_suppression_and_stop():
    with session() as db, db.begin():
        svc.register_destination(db, 'BW-1041', '+447911123456', 'Isolated scheduler consent; never dial')
        db.scalar(select(m.Obligation).where(m.Obligation.property_id == 'BW-1041-P1')).due_date = date(2026, 11, 25)
        db.flush()
        first = enqueue_due(db, AT)
        assert len(first) == 1
        assert enqueue_due(db, AT) == first
        assert db.scalar(select(func.count()).select_from(m.Outbox)) == 1
        call = db.get(m.Call, first[0])
        call.state = 'finished'
        db.get(m.CampaignContact, db.scalar(select(m.CampaignContact.id))).stopped = True
        assert enqueue_due(db, AT + timedelta(days=1)) == []


def test_unqualified_campaign_does_not_silently_use_the_indian_route():
    cfg = settings().model_copy(update={'campaign_gateway_url':'https://voice.example.test',
        'campaign_gateway_token':SecretStr('x' * 40), 'managed_enabled':True,
        'managed_campaign_agent_id':'separate-campaign', 'office_callback_number':'+441632960418'})
    issues = configuration_issues(cfg)
    assert any('Qualify the UK' in x for x in issues)
    assert any('real approved UK' in x for x in issues)


@pytest.mark.parametrize('disposition', ['not_interested', 'serviced_elsewhere', 'not_available'])
def test_dynamic_outcome_uses_original_turn_and_stops_only_the_right_retry_policy(disposition):
    from test_managed_phone import event
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        text = 'A contextual caller statement, interpreted separately by the real-model checks'
        event(db, call, 'user_utterance', now() - timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text=text, speech_timing_verified=True)
        conv.user(text)
        evidence = bind(db, conv, disposition=disposition)
        record_meaning(db, call, evidence)
        record_meaning(db, call, evidence)
        assert db.scalar(select(func.count()).select_from(m.CallEvent).where(m.CallEvent.kind == disposition)) == 1
        svc.finalise(db, call, 'Current caller decision recorded')
        assert call.outcome == {'not_interested':'Not interested','serviced_elsewhere':'Serviced elsewhere','not_available':'Not available'}[disposition]


def test_a_completed_conversation_without_saved_resolution_reaches_sarah_once():
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.conversation = True
        svc.finalise(db, call, 'Booking could not be completed; no callback was promised')
        svc.finalise(db, call, call.summary)
        rows = list(db.scalars(select(m.Followup).where(m.Followup.call_id == call.id)))
        assert len(rows) == 1 and rows[0].kind == 'internal_review' and rows[0].owner == 'Sarah'


def test_campaign_voicemail_has_one_privacy_safe_approved_message(monkeypatch):
    from test_call_boundaries import turn
    cfg = settings().model_copy(update={'office_callback_number':'+442079460123'})
    monkeypatch.setattr('brightwater.config.settings', lambda:cfg)
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        call.purpose = 'campaign'
        call.identity_verified = False
        proof = turn(db, call, conv, 0, 'voicemail', warning=False)
        first = voicemail_result(db, call, proof)
        assert first['message_allowed'] and '02079460123' in first['approved_message']
        assert 'Albert' not in first['approved_message'] and 'Helen' not in first['approved_message'] and 'boiler' not in first['approved_message']
        assert not voicemail_result(db, call, proof)['message_allowed']
        svc.finalise(db, call, 'Voicemail reached; message authorisation checked')
        assert call.outcome == 'Voicemail'


def test_campaign_profile_preserves_voice_turn_settings_and_has_truthful_opening():
    from brightwater.managed.agent import config
    engineering = config(phone=True)
    campaign = config(phone=True, campaign=True)
    for key in ['tts','asr','turn']:
        assert engineering['conversation_config'][key] == campaign['conversation_config'][key]
    assert campaign['conversation_config']['conversation']['max_duration_seconds'] == 900
    assert engineering['conversation_config']['conversation']['max_duration_seconds'] == 7200
    opening = campaign['conversation_config']['agent']['first_message']
    assert 'automated assistant' in opening and 'Brightwater Plumbing' in opening and 'fictional' not in opening
    assert 'verified live account and diary tools' in campaign['conversation_config']['agent']['prompt']['prompt']


def test_campaign_gateway_admission_is_bound_to_current_token_destination_and_pause(monkeypatch):
    from fastapi.testclient import TestClient

    import brightwater.api as api
    cfg = settings().model_copy(update={'dialing_enabled':True, 'managed_enabled':True,
        'managed_campaign_agent_id':'isolated-native-agent', 'managed_api_key':SecretStr('test-key'),
        'managed_webhook_secret':SecretStr('x' * 40), 'campaign_gateway_url':'https://uk.example.test',
        'campaign_gateway_token':SecretStr('y' * 40), 'campaign_route_verified':True,
        'office_callback_number':'+442079460123', 'recording_notice':'This call is recorded'})
    monkeypatch.setattr(api, 'settings', lambda:cfg)
    monkeypatch.setattr(api, 'now', lambda:AT)
    with session() as db, db.begin():
        call, token = make_call(db)
        call.state, call.dispatched_at = 'dispatching', AT
        db.get(m.Control, 'dialing').enabled = True
        cid = call.id
    client = TestClient(api.app)
    body = {'call_id':cid,'phone':'+447911123456','session_token':token}
    headers = {'Authorization':'Bearer '+cfg.runtime_token.get_secret_value()}
    assert client.post('/internal/campaign/admission',json=body).status_code == 401
    assert client.post('/internal/campaign/admission',headers=headers,json={**body,'phone':'+447911654321'}).status_code == 403
    assert client.post('/internal/campaign/admission',headers=headers,json={**body,'session_token':'wrong-token'}).status_code == 403
    assert client.post('/internal/campaign/admission',headers=headers,json=body).status_code == 200
    with session() as db, db.begin():
        db.get(m.Control,'dialing').enabled = False
    assert client.post('/internal/campaign/admission',headers=headers,json=body).status_code == 403


def test_reported_urgent_problem_reaches_sarah_once_even_before_tool_and_is_not_duplicated():
    from test_managed_phone import event
    with session() as db, db.begin():
        call, conv, _ = phone(db)
        text = 'There is no heating or hot water at the house.'
        event(db, call, 'user_utterance', now() - timedelta(seconds=1), source='plivo_elevenlabs_observer',
              text=text, speech_timing_verified=True)
        conv.user(text)
        proof = bind(db, conv, followup='urgent', followup_basis='explicit')
        record_meaning(db, call, proof)
        result = conv.execute(db,'record_followup',{'kind':'urgent'},'urgent-tool')
        assert result['saved']
        rows = list(db.scalars(select(m.Followup).where(m.Followup.call_id==call.id)))
        assert len(rows)==1 and rows[0].owner=='Sarah' and rows[0].priority==0 and rows[0].detail==text
        svc.finalise(db,call,'Urgent office handover recorded')
        assert call.outcome=='Urgent callback'


def test_ageing_boiler_quote_is_offered_once_before_readback_and_never_reopens_saved_booking():
    from test_managed_phone import phone
    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        db.get(m.Property,'BW-1041-P1').boiler_year = 2000
        offer = db.scalar(select(m.AvailabilityOffer).where(m.AvailabilityOffer.call_id==call.id))
        result = conv.execute(db,'prepare_booking',{'offer_id':offer.id,'tenants':[]},'old-boiler-prepare')
        assert result['optional_quote_offer'] is True and result['confirmed'] is False
        assert result['proposal_id']==prepared['proposal_id']
        repeated = conv.execute(db,'prepare_booking',{'offer_id':offer.id,'tenants':[]},'old-boiler-repeat')
        assert repeated['optional_quote_offer'] is False
        assert not list(db.scalars(select(m.Followup).where(m.Followup.kind=='lead'))), 'Age alone is not customer interest'
