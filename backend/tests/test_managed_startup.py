"""Connection warm-up cannot bypass call admission or disclose its capability."""
import asyncio
import json
import time

import httpx
import pytest
from conftest import make_call
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from brightwater import models as m
from brightwater.config import settings
from brightwater.db import session
from brightwater.managed import startup


class Cache:
    def __init__(self):
        self.data = {}

    def getdel(self, key):
        return self.data.pop(key, None)

    def set(self, key, value, **kwargs):
        if kwargs.get("nx") and key in self.data:
            return False
        self.data[key] = value
        return True

    def setex(self, key, ttl, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def eval(self, script, count, key, expected):
        if self.data.get(key) == expected:
            del self.data[key]
            return 1
        return 0


@pytest.fixture
def prepared(monkeypatch):
    cfg = settings().model_copy(update={"managed_enabled": True, "managed_phone_enabled": True,
        "managed_agent_id": "agent_browser_fixture", "managed_phone_agent_id": "agent_phone_fixture",
        "managed_api_key": SecretStr("fixture-provider-key"), "managed_webhook_secret": SecretStr("w" * 40),
        "engineering_recipient": SecretStr("+919876543210"),
        "media_encryption_key": SecretStr(Fernet.generate_key().decode())})
    monkeypatch.setattr(startup, "settings", lambda: cfg)
    from brightwater.managed import gateway
    monkeypatch.setattr(gateway, "settings", lambda: cfg)
    cache = Cache()
    monkeypatch.setattr(gateway, "broker", lambda: cache)
    url = "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=agent_phone_fixture&token=fixture-capability"
    return cfg, cache, url


def put(cache, cfg, url, call_id="fixture-call", **overrides):
    payload = {"call_id": call_id, "agent_id": cfg.managed_phone_agent_id,
               "created_at": time.time(), "signed_url": url} | overrides
    raw = Fernet(cfg.media_encryption_key.get_secret_value().encode()).encrypt(json.dumps(payload).encode())
    cache.set("managed:prepared-phone:" + call_id, raw)
    return raw


def test_prepared_capability_is_encrypted_and_consumed_once(prepared):
    cfg, cache, url = prepared
    raw = put(cache, cfg, url)
    assert url.encode() not in raw and b"fixture-capability" not in raw
    assert startup.consume(cache, "fixture-call", cfg) == url
    assert startup.consume(cache, "fixture-call", cfg) is None


@pytest.mark.parametrize("change", [
    {"agent_id": "different-agent"}, {"created_at": 0}, {"created_at": time.time() + 100},
    {"signed_url": "wss://api.elevenlabs.io.attacker.test/v1/convai/conversation"},
    {"signed_url": "wss://user:pass@api.elevenlabs.io/v1/convai/conversation"},
    {"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=other&token=x"},
])
def test_invalid_preparation_falls_back_without_reusing_capability(prepared, change):
    cfg, cache, url = prepared
    put(cache, cfg, url, **change)
    assert startup.consume(cache, "fixture-call", cfg) is None


def test_cached_session_keeps_double_auth_and_avoids_external_request(prepared, monkeypatch):
    from brightwater.api import app
    cfg, cache, url = prepared
    with session() as db, db.begin():
        call, token = make_call(db)
        call.purpose = "engineering"
        db.get(m.Destination, call.destination_id).phone = cfg.engineering_recipient.get_secret_value()
        call_id = call.id
    put(cache, cfg, url, call_id)
    def forbidden(*args, **kwargs):
        raise AssertionError("A prepared session must not repeat provider HTTP")
    client = TestClient(app)
    monkeypatch.setattr("brightwater.managed.gateway.httpx.Client", forbidden)
    assert client.post("/runtime/managed/session").status_code == 401
    assert "managed:prepared-phone:" + call_id in cache.data
    response = client.post("/runtime/managed/session", headers={"Authorization": "Bearer " + token,
        "X-Brightwater-Runtime": cfg.runtime_token.get_secret_value()})
    assert response.status_code == 200
    assert response.json()["signed_url"] == url
    assert "managed:prepared-phone:" + call_id not in cache.data
    assert cache.get("managed:lease")
    client.close()


@pytest.mark.parametrize("state,purpose,expected_requests", [
    ("dispatching", "engineering", 1), ("in_progress", "engineering", 1),
    ("finished", "engineering", 0), ("in_progress", "campaign", 0),
])
def test_background_preparation_requires_existing_live_engineering_intent(prepared, monkeypatch, state, purpose, expected_requests):
    cfg, cache, url = prepared
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.state, call.purpose = state, purpose
        call_id = call.id
    requests = []
    class Provider:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, path, **kwargs):
            requests.append(path)
            assert path.endswith("/get-signed-url")
            return httpx.Response(200, json={"signed_url": url}, request=httpx.Request("GET", path))
    monkeypatch.setattr(startup.httpx, "AsyncClient", Provider)
    asyncio.run(startup.prepare(call_id))
    assert len(requests) == expected_requests
    assert bool(cache.get("managed:prepared-phone:" + call_id)) == bool(expected_requests)


def test_preparation_failure_does_not_change_or_retry_call(prepared, monkeypatch):
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.state, call.purpose = "dispatching", "engineering"
        call_id = call.id
    class Unavailable:
        def __init__(self, **kwargs):
            raise httpx.ConnectError("Synthetic provider unavailable")
    monkeypatch.setattr(startup.httpx, "AsyncClient", Unavailable)
    asyncio.run(startup.prepare(call_id))
    with session() as db:
        assert db.get(m.Call, call_id).state == "dispatching"


def test_caption_warms_facts_but_cannot_authorise_a_booking(prepared, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import func, select

    from brightwater.managed import semantic_runtime, understanding
    from brightwater.managed.phone import commit
    from brightwater.policy import Rejected, now

    cfg, cache, _ = prepared
    monkeypatch.setattr(semantic_runtime, "settings", lambda: cfg)
    text = "At eighteen Albert Road, Southsea, PO4 zero JT, the service is ninety-five pounds including VAT. Shall I book it?"
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.purpose = "engineering"
        proposal = m.Proposal(call_id=call.id, items=[], fingerprint="f" * 64, total_pence=9500,
            created_at=now() - timedelta(seconds=3), expires_at=now() + timedelta(minutes=2))
        db.add(proposal)
        caption = m.CallEvent(call_id=call.id, provider_event_id=m.uid(), kind="turn_state",
            occurred_at=now() - timedelta(seconds=1), payload={"source": "managed_agent_prompt",
            "completed": False, "text": text})
        db.add(caption)
        db.flush()
        call_id, caption_id, proposal_id = call.id, caption.id, proposal.id
    analysed = []
    monkeypatch.setattr(understanding, "extract_facts", lambda value, **kwargs: analysed.append(value))
    semantic_runtime.prefetch_readback(call_id, caption_id)
    assert analysed == [text]
    with session() as db, db.begin():
        call = db.get(m.Call, call_id)
        db.add(m.CallEvent(call_id=call.id, provider_event_id=m.uid(), kind="user_utterance",
            occurred_at=now(), payload={"source": "plivo_elevenlabs_observer", "speech_timing_verified": True,
                                      "text": "Yes, book it."}))
        db.flush()
        with pytest.raises(Rejected, match="Read all the prepared details"):
            commit(db, call, proposal_id, "Yes, book it.")
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
        assert db.get(m.Proposal, proposal_id).state == "prepared"
        assert db.scalar(select(func.count()).select_from(m.CallEvent).where(m.CallEvent.kind == "readback_completed")) == 0
