"""Long attended sessions keep tool access and retain bounded call ownership."""
import asyncio
import json
from datetime import timedelta
from xml.etree.ElementTree import fromstring

import httpx
import pytest
from conftest import make_call
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brightwater import models as m
from brightwater.api import app
from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS, ATTENDED_SESSION_TTL_SECONDS
from brightwater.db import session
from brightwater.managed.agent import config
from brightwater.managed.engine import Conversation
from brightwater.managed.gateway import reap_closed_phone_lease
from brightwater.plivo_client import PlivoClient, PlivoCredentials
from brightwater.plivo_gateway import Outbound, answer_xml
from brightwater.policy import Rejected, now


def test_attended_duration_reaches_carrier_recording_and_native_agent():
    body = Outbound(call_id="11111111-1111-1111-1111-111111111111", session_token="fixture",
        phone="+919876543210", purpose="engineering")
    assert body.max_seconds == ATTENDED_CALL_MAX_SECONDS == 7200
    with pytest.raises(ValidationError):
        body.model_validate({**body.model_dump(), "max_seconds": 7201})
    from types import SimpleNamespace
    root = fromstring(answer_xml(SimpleNamespace(gateway_origin="https://voice.example.test",
        gateway_diagnostic_hold=False), "fixture", "not-real", body.max_seconds))
    assert root.find("Record").get("maxLength") == "7200"
    assert config("kb", phone=True)["conversation_config"]["conversation"]["max_duration_seconds"] == 7200
    assert config("kb", phone=False)["conversation_config"]["conversation"]["max_duration_seconds"] == 180
    assert ATTENDED_SESSION_TTL_SECONDS > ATTENDED_CALL_MAX_SECONDS


def test_carrier_request_retains_explicit_two_hour_ceiling_without_real_call():
    async def run():
        requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"request_uuid": "fixture-request"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            carrier = PlivoClient(client, PlivoCredentials("fixture", "not-real"))
            await carrier.make_call(from_number="+911234567890", to_number="+919876543210",
                answer_url="https://example.test/answer", hangup_url="https://example.test/end")
            assert requests[0]["time_limit"] == 7200
            with pytest.raises(ValueError):
                await carrier.make_call(from_number="x", to_number="y", answer_url="x", hangup_url="y", max_seconds=7201)
            assert len(requests) == 1
    asyncio.run(run())


@pytest.mark.parametrize("purpose,minutes,status", [("engineering", 70, 200), ("engineering", 126, 401), ("campaign", 70, 401)])
def test_scoped_credentials_support_long_engineering_calls_without_extending_campaigns(purpose, minutes, status):
    with session() as db, db.begin():
        call, token = make_call(db)
        call.purpose, call.created_at = purpose, now() - timedelta(minutes=minutes)
        call_id = call.id
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + token}
        assert client.get("/runtime/account", headers=headers).status_code == status
        if status == 200:
            with session() as db, db.begin():
                db.get(m.Call, call_id).state = "finished"
            assert client.get("/runtime/account", headers=headers).status_code == 401


def test_phone_business_tools_work_after_four_minutes_but_not_after_session_end():
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose, call.created_at = "engineering", now() - timedelta(minutes=10)
        conv = Conversation(call.id, trusted_phone=True)
        conv.user("Please check the diary")
        result = conv.execute(db, "check_availability", {"items": [{"property_id": "BW-1041-P1", "service": "service"}]}, "long-call")
        assert "options" in result
        call.state = "finished"
        with pytest.raises(Rejected, match="expired or closed"):
            conv.execute(db, "check_availability", {"items": []}, "ended-call")


@pytest.mark.parametrize("state,replaced", [("in_progress", False), ("finished", False), ("failed", False), ("finished", True)])
def test_ended_phone_lease_does_not_block_next_test_or_release_another_owner(state, replaced):
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose, call.state = "engineering", state
        call_id = call.id
    class Broker:
        def __init__(self):
            self.values = {"managed:lease": "old-owner", "managed:cap:old-owner": json.dumps({"id": call_id, "storage": "phone"})}
        def get(self, key):
            return self.values.get(key)
        def eval(self, script, count, key, owner):
            if replaced:
                self.values[key] = "new-owner"
            if self.values.get(key) == owner:
                self.values.pop(key)
    broker = Broker()
    reap_closed_phone_lease(broker)
    assert broker.get("managed:lease") == ("old-owner" if state == "in_progress" else "new-owner" if replaced else None)


def test_phone_tool_capability_and_lease_outlive_the_attended_duration(monkeypatch):
    from pydantic import SecretStr

    from brightwater.config import settings
    from brightwater.managed import gateway

    cfg = settings()
    for key, value in {"managed_enabled": True, "managed_phone_enabled": True,
        "managed_agent_id": "fixture-browser", "managed_phone_agent_id": "fixture-phone",
        "managed_api_key": SecretStr("not-real"), "managed_webhook_secret": SecretStr("s" * 40),
        "engineering_recipient": SecretStr("+919876543210")}.items():
        monkeypatch.setattr(cfg, key, value)
    class Broker:
        def __init__(self):
            self.values, self.ttls = {}, {}
        def get(self, key):
            return self.values.get(key)
        def set(self, key, value, *, nx=False, ex=None):
            if nx and key in self.values:
                return False
            self.values[key], self.ttls[key] = value, ex
            return True
        def setex(self, key, ttl, value):
            self.values[key], self.ttls[key] = value, ttl
    class Provider:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request("GET", url), json={"signed_url": "wss://api.elevenlabs.io/fixture"})
    broker = Broker()
    monkeypatch.setattr(gateway, "broker", lambda: broker)
    monkeypatch.setattr(gateway.httpx, "Client", Provider)
    with session() as db, db.begin():
        call, token = make_call(db)
        call.purpose = "engineering"
        db.get(m.Destination, call.destination_id).phone = cfg.engineering_recipient.get_secret_value()
    with TestClient(app) as client:
        response = client.post("/runtime/managed/session", headers={"Authorization": "Bearer " + token,
            "X-Brightwater-Runtime": cfg.runtime_token.get_secret_value()})
    assert response.status_code == 200
    assert broker.ttls["managed:lease"] >= 7200
    assert next(ttl for key, ttl in broker.ttls.items() if key.startswith("managed:cap:")) >= 7200


def test_long_phone_history_does_not_extend_automated_evaluation_history():
    from brightwater.managed.gateway import conversation_from_history

    raw = json.dumps({"x-elevenlabs-history": True,
        "entries": [{"role": "user", "message": "Conversation detail " * 15} for _ in range(600)]})
    assert len(conversation_from_history("fixture", False, raw, {"storage": "phone"}).turns) == 600
    with pytest.raises(Rejected, match="exceeds the limit"):
        conversation_from_history("fixture", False, raw, {})
