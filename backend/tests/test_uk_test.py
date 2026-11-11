from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from brightwater import models as m
from brightwater.api import app
from brightwater.config import settings
from brightwater.db import session
from brightwater.policy import Rejected
from brightwater.schemas import UKTestInput
from brightwater.uk_test import is_uk_test, normalise_phone, prepare

RECIPIENT = "+442079460123"


@pytest.fixture
def enabled_pilot(monkeypatch):
    cfg = settings()
    for key, value in {
        "environment": "staging",
        "uk_test_enabled": True,
        "uk_test_caller_id": SecretStr("+442079460124"),
        "campaign_gateway_url": "https://voice.example.test",
        "campaign_gateway_token": SecretStr("synthetic" * 5),
        "managed_campaign_agent_id": "agent_fixture",
        "managed_enabled": True,
        "managed_phone_enabled": True,
        "media_encryption_key": SecretStr("synthetic"),
    }.items():
        monkeypatch.setattr(cfg, key, value)
    at = datetime(2026, 11, 11, 13, tzinfo=UTC)
    monkeypatch.setattr("brightwater.uk_test.now", lambda: at)
    monkeypatch.setattr("brightwater.api.now", lambda: at)
    return cfg


def payload(**overrides):
    return UKTestInput(**({"customer_id": "BW-1041", "phone": "020 7946 0123",
                           "consent": True, "request_key": str(uuid4())} | overrides))


@pytest.mark.parametrize("hour,customer_id", [(13, "BW-1041"), (20, "BW-1041"), (11, "BW-1093")])
def test_uk_test_admission_is_idempotent_and_never_enables_campaign(enabled_pilot, monkeypatch, hour, customer_id):
    cfg = enabled_pilot
    at = datetime(2026, 11, 11, hour, tzinfo=UTC)
    monkeypatch.setattr("brightwater.uk_test.now", lambda: at)
    monkeypatch.setattr("brightwater.api.now", lambda: at)
    body = payload(customer_id=customer_id)
    with session() as db, db.begin():
        call, token = prepare(db, cfg, body)
        assert is_uk_test(call)
        assert db.get(m.Destination, call.destination_id).phone == RECIPIENT
        assert not db.scalar(select(m.Outbox.id))
        assert not cfg.dialing_enabled
        again, other_token = prepare(db, cfg, body)
        assert again.id == call.id and other_token is None
        call_id = call.id

    client = TestClient(app)
    path = "/internal/campaign/admission"
    request = {"call_id": call_id, "session_token": token, "phone": RECIPIENT}
    assert client.post(path, json=request).status_code == 401
    headers = {"Authorization": "Bearer " + cfg.runtime_token.get_secret_value()}
    assert client.post(path, headers=headers, json=request).status_code == 200
    assert client.post(path, headers=headers, json=request | {"phone": "+442079460125"}).status_code == 403
    with session() as db, db.begin():
        db.add(m.Control(key="uk_test", enabled=False))
    assert client.post(path, headers=headers, json=request).status_code == 403


@pytest.mark.parametrize("updates,code", [
    ({"consent": False}, "consent_required"),
    ({"phone": "+447700900123"}, "fictional_destination"),
    ({"phone": "+442079460124"}, "invalid_destination"),
    ({"phone": "+919876543210"}, "invalid_destination"),
])
def test_uk_test_rejects_unsafe_destinations(enabled_pilot, updates, code):
    with session() as db, db.begin(), pytest.raises(Rejected) as error:
        prepare(db, enabled_pilot, payload(**updates))
    assert error.value.code == code


def test_uk_test_honours_global_suppression(enabled_pilot):
    with session() as db, db.begin():
        db.add(m.Suppression(phone=RECIPIENT, evidence="fictional test"))
        db.flush()
        with pytest.raises(Rejected) as error:
            prepare(db, enabled_pilot, payload())
        assert error.value.code == "suppressed"
    assert normalise_phone("0044 (20) 7946-0123") == RECIPIENT
