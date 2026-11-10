"""Prepare a short-lived private provider URL while an authorised phone rings.

This creates no carrier request, business session or account authority. The normal
active-call and trusted-gateway checks still run before consuming the URL.
"""
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater.config import settings
from brightwater.db import engine

TTL_SECONDS = 45


def valid_url(value, agent_id):
    if not isinstance(value, str):
        return False
    url = urlparse(value)
    query = parse_qs(url.query)
    return (url.scheme == "wss" and url.hostname == "api.elevenlabs.io"
            and url.path == "/v1/convai/conversation" and not url.username and not url.password
            and url.port in {None, 443} and query.get("agent_id") == [agent_id]
            and len(query.get("token", [])) == 1 and bool(query["token"][0]))


def consume(redis, call_id, cfg):
    try:
        raw = redis.getdel("managed:prepared-phone:" + call_id)
        if not raw:
            return None
        value = json.loads(Fernet(cfg.media_encryption_key.get_secret_value().encode()).decrypt(raw))
        if (value["call_id"] == call_id and value["agent_id"] == cfg.managed_phone_agent_id
                and 0 <= time.time() - value["created_at"] < TTL_SECONDS
                and valid_url(value["signed_url"], cfg.managed_phone_agent_id)):
            return value["signed_url"]
    except Exception:
        pass
    return None


async def prepare(call_id):
    """Best-effort background preparation after the sole carrier POST succeeded."""
    cfg = settings()
    if not (cfg.managed_enabled and cfg.managed_phone_enabled and cfg.managed_phone_agent_id
            and cfg.media_encryption_key.get_secret_value()):
        return
    try:
        with Session(engine()) as db:
            call = db.get(m.Call, call_id)
            if not call or call.purpose != "engineering" or call.state not in {"dispatching", "in_progress"}:
                return
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                headers={"xi-api-key": cfg.managed_api_key.get_secret_value()},
                params={"agent_id": cfg.managed_phone_agent_id})
            response.raise_for_status()
        url = response.json()["signed_url"]
        if not valid_url(url, cfg.managed_phone_agent_id):
            return
        with Session(engine()) as db:
            call = db.get(m.Call, call_id)
            if not call or call.state not in {"dispatching", "in_progress"}:
                return
        value = {"call_id": call_id, "agent_id": cfg.managed_phone_agent_id,
                 "created_at": time.time(), "signed_url": url}
        from brightwater.managed.gateway import broker
        encrypted = Fernet(cfg.media_encryption_key.get_secret_value().encode()).encrypt(json.dumps(value).encode())
        redis = broker()
        redis.set("managed:prepared-phone:" + call_id, encrypted, ex=TTL_SECONDS, nx=True)
        redis.setex("managed:phone-startup-meta:" + call_id, 86400, json.dumps({
            "prepared_at": time.time(), "provider_preparation_seconds": time.perf_counter() - started}))
    except Exception:
        # The authorised session path falls back to its normal provider request.
        # An optional warm-up must never trigger, retry or terminate a call.
        return
