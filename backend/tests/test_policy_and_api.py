from datetime import UTC, datetime, time

import pytest
from conftest import make_call
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.api import app
from brightwater.config import Settings, settings
from brightwater.db import session
from brightwater.policy import (
    Rejected,
    allowed_time,
    explicit_opt_out,
    next_retry,
    time_band,
    uk_phone,
)


@pytest.mark.parametrize("at,preference,expected", [
    ("2026-11-05T09:59:00+00:00", None, False),
    ("2026-11-05T10:00:00+00:00", None, True),
    ("2026-11-05T19:25:00+00:00", None, True),
    ("2026-11-05T19:30:00+00:00", None, False),
    ("2026-11-07T12:54:00+00:00", None, True),
    ("2026-11-07T12:55:00+00:00", None, True),
    ("2026-11-07T13:00:00+00:00", None, False),
    ("2026-11-08T12:00:00+00:00", None, False),
    ("2026-11-05T11:59:00+00:00", time(12), False),
    ("2026-07-06T09:00:00+00:00", None, True),  # 10:00 BST, not fixed UTC
])
def test_calling_windows(at, preference, expected):
    assert allowed_time(datetime.fromisoformat(at), preference) is expected


def test_retry_observes_24_hours_new_date_and_band():
    start = datetime(2026, 11, 5, 18, tzinfo=UTC)
    retry = next_retry(start, {time_band(start)}, time(12))
    assert (retry - start).total_seconds() >= 86400
    assert retry.date() > start.date()
    assert time_band(retry) != time_band(start)
    assert allowed_time(retry, time(12))


@pytest.mark.parametrize("phone", ["+447700900714", "+441632960418", "+919876543210", "07700900714"])
def test_never_dial_fictional_or_non_uk_destinations(phone):
    with pytest.raises(Rejected):
        uk_phone(phone)


def test_source_records_have_no_diallable_destination():
    with session() as db:
        assert db.scalar(select(func.count()).select_from(m.Customer)) == 8
        assert db.scalar(select(func.count()).select_from(m.Destination)) == 0
        assert db.scalar(select(func.sum(m.DiaryWindow.capacity_minutes))) == 10800
        assert db.scalar(select(func.sum(m.DiaryWindow.used_minutes))) == 5400


def test_operator_authentication_and_disabled_dial_route():
    client = TestClient(app)
    assert client.get("/v1/dashboard").status_code == 401
    response = client.post("/v1/calls", headers={"Authorization": "Bearer " + settings().operator_token.get_secret_value()},
                           json={"customer_id": "BW-1041", "request_key": "test-request-123"})
    assert response.status_code == 409
    assert response.json()["error"] == "dialing_disabled"
    with session() as db:
        assert db.scalar(select(func.count()).select_from(m.Call)) == 0


def test_customer_details_are_hidden_until_named_identity():
    with session() as db, db.begin():
        _, token = make_call(db, verified=False)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/runtime/account", headers=headers).status_code == 403
    result = client.get("/runtime/context", headers=headers)
    assert result.status_code == 200
    assert "address" not in result.text and "boiler" not in result.text


def test_session_cannot_read_another_customers_record_or_inject_fields():
    with session() as db, db.begin():
        _, token = make_call(db)
    client = TestClient(app)
    response = client.post("/runtime/availability", headers={"Authorization": f"Bearer {token}"},
                           json={"items": [{"property_id": "BW-1056-P1", "service": "cp12"}]})
    assert response.status_code == 422
    response = client.post("/runtime/availability", headers={"Authorization": f"Bearer {token}"},
                           json={"items": [{"property_id": "BW-1041-P1", "service": "service", "price_pence": 1}]})
    assert response.status_code == 422


def test_suppression_survives_new_campaign_and_destination_update():
    with session() as db, db.begin():
        call, _ = make_call(db)
        event = svc.record_event(db, call.id, s.EventInput(provider_event_id="optout", kind="user_utterance",
            occurred_at=datetime.now(UTC), payload={"text": "Please stop calling me"}))
        svc.suppress(db, call, event.id)
        customer_id = call.customer_id
    with session() as db, db.begin(), pytest.raises(Rejected) as caught:
        svc.register_destination(db, customer_id, "+447911654321", "Another offline test destination")
    assert caught.value.code == "suppressed"


def test_duplicate_events_are_idempotent_and_collisions_rejected():
    with session() as db, db.begin():
        call, _ = make_call(db)
        body = s.EventInput(provider_event_id="same", kind="complaint", occurred_at=datetime.now(UTC), payload={"detail": "Late engineer"})
        first = svc.record_event(db, call.id, body)
        second = svc.record_event(db, call.id, body)
        assert first.id == second.id
        assert db.scalar(select(func.count()).select_from(m.Followup)) == 1
        with pytest.raises(Rejected):
            svc.record_event(db, call.id, body.model_copy(update={"payload": {"detail": "different"}}))


def test_shadow_cannot_be_configured_to_dial():
    data = settings().model_dump()
    data.update(environment="shadow", dialing_enabled=True)
    with pytest.raises(ValueError, match="forbidden"):
        Settings(**data)


def test_dashboard_never_invents_quality_scores_or_completed_calls():
    result = TestClient(app).get("/v1/dashboard", headers={"Authorization": "Bearer " + settings().operator_token.get_secret_value()})
    assert result.status_code == 200
    assert result.json()["quality"] == {"status": "NOT EVALUATED", "voice_score": None, "conversation_score": None}
    assert result.json()["metrics"]["called"] == 0


@pytest.mark.parametrize("utterance", [
    "Please stop calling me.", "Stop phoning this number, please!", "Don't call me again.",
    "Please remove me from your calling list, thank you", "Take this number off your list",
])
def test_clear_opt_out_is_suppressed_without_model_tool_or_identity(utterance):
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        body = s.EventInput(provider_event_id="independent-optout", kind="user_utterance",
            occurred_at=datetime.now(UTC), payload={"text": utterance})
        first = svc.record_event(db, call.id, body)
        assert svc.record_event(db, call.id, body).id == first.id
        assert db.scalar(select(func.count()).select_from(m.Suppression)) == 1
        assert not db.get(m.Destination, call.destination_id).enabled
        assert not call.identity_verified
        assert svc.suppressed(db, call.customer_id, "+447911123456")
        assert svc.finalise(db, call, "The caller opted out.").outcome == "Do not call"


@pytest.mark.parametrize("utterance", [
    "Don't stop calling me", "I didn't say stop calling me", "She said stop calling me",
    "What happens if I say stop calling me?", "Stop calling the boiler old",
    "Please call me again", "I want a boiler service", "", None,
])
def test_opt_out_backstop_does_not_infer_negation_or_quoted_commands(utterance):
    assert not explicit_opt_out(utterance)


@pytest.mark.parametrize("utterance", ["Please stop recording", "Don't record this call", "I don't consent to recording"])
def test_recording_refusal_closes_account_access_without_claiming_no_answer(utterance):
    with session() as db, db.begin():
        call, _ = make_call(db)
        event = s.EventInput(provider_event_id="recording-refusal", kind="user_utterance",
            occurred_at=datetime.now(UTC), payload={"text": utterance})
        svc.record_event(db, call.id, event)
        assert not call.identity_verified and call.state == "finished"
        assert call.outcome is None
        assert "declined recording" in call.summary
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
        assert svc.record_event(db, call.id, event).id
        assert db.scalar(select(func.count()).select_from(m.CallEvent).where(m.CallEvent.kind == "recording_refused")) == 1
