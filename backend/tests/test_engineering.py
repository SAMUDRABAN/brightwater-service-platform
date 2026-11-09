from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.db import session
from brightwater.engineering import prepare_engineering
from brightwater.plivo_client import PlivoClient, PlivoCredentials, PlivoRequestUncertain
from brightwater.policy import Rejected, uk_phone


def config(**updates):
    values = dict(engineering_enabled=True, environment="staging", engineering_recipient=SecretStr("+919876543210"),
        engineering_consent_reference="Explicit offline integration test consent; never dial", engineering_display_name="Test recipient",
        engineering_call_limit=3, release_id="test")
    return SimpleNamespace(**(values | updates))


def test_engineering_call_is_allowlisted_separate_and_idempotent():
    with session() as db, db.begin():
        call, token = prepare_engineering(db, config(), "owned-test-request")
        same, replay_token = prepare_engineering(db, config(), "owned-test-request")
        assert call.id == same.id and replay_token is None and token
        assert call.purpose == "engineering" and call.state == "dispatching"
        assert db.get(m.Customer, call.customer_id).notes.startswith("ATTENDED ENGINEERING")
        assert db.get(m.Destination, call.destination_id).phone == config().engineering_recipient.get_secret_value()
        with pytest.raises(Rejected) as error:
            prepare_engineering(db, config(), "second-request")
        assert error.value.code == "call_in_progress"
        with pytest.raises(Rejected):
            uk_phone(config().engineering_recipient.get_secret_value())


def test_engineering_disabled_and_opt_out_prevents_future_tests():
    with session() as db, db.begin():
        with pytest.raises(Rejected):
            prepare_engineering(db, config(engineering_enabled=False), "off-request")
        call, _ = prepare_engineering(db, config(), "first-request")
        call.state = "in_progress"
        svc.record_event(db, call.id, s.EventInput(provider_event_id="stop", kind="user_utterance",
            occurred_at=datetime.now(UTC), payload={"text": "Please stop calling me"}))
        svc.finalise(db, call, "Recipient requested permanent suppression.")
        with pytest.raises(Rejected) as result:
            prepare_engineering(db, config(), "later-request")
        assert result.value.code == "suppressed"
        assert db.scalar(select(m.Suppression.phone)) == "+919876543210"


def test_plivo_client_does_not_retry_uncertain_initiation_or_hangup_all():
    import asyncio

    async def run():
        attempts = []

        def handler(request):
            attempts.append(request)
            return httpx.Response(500)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = PlivoClient(http, PlivoCredentials("test-account", "not-a-real-token"))
            with pytest.raises(PlivoRequestUncertain):
                await client.make_call(from_number="+911234567890", to_number="+919876543210",
                    answer_url="https://example.test/answer", hangup_url="https://example.test/status")
            assert len(attempts) == 1
            with pytest.raises(ValueError):
                await client.hangup("")
            assert len(attempts) == 1
    asyncio.run(run())


def test_unreachable_voice_gateway_cannot_create_a_dial_intent(monkeypatch):
    from fastapi.testclient import TestClient

    from brightwater import api
    from brightwater.config import settings

    cfg = settings().model_copy(update={"engineering_enabled": True, "voice_gateway_url": "https://voice.example.test"})
    monkeypatch.setattr(api, "settings", lambda: cfg)

    class Unreachable:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            raise httpx.ConnectError("Synthetic unavailable transport")

    monkeypatch.setattr(api.httpx, "AsyncClient", Unreachable)
    response = TestClient(api.app).post("/v1/engineering/calls",
        headers={"Authorization": "Bearer " + cfg.operator_token.get_secret_value()},
        json={"request_key": "unreachable-route-request"})
    assert response.status_code == 503
    assert response.json()["error"] == "voice_gateway_unavailable"
    with session() as db:
        assert db.scalar(select(m.Call.id)) is None
