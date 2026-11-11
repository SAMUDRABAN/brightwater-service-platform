"""Authenticated direct Plivo media gateway, run as one worker near the carrier.

This gateway does real provider work only after explicit authenticated admission.
Engineering calls have one private allowlist and a three-minute hard limit.
"""
import asyncio
import contextlib
import io
import json
import math
import secrets
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Literal
from urllib.parse import parse_qsl, urlparse
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis

from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS, MAX_CARRIER_RECORDING_BYTES
from brightwater.plivo_client import PlivoClient, PlivoCredentials
from brightwater.plivo_security import (
    configured_external_url,
    create_stream_token,
    verify_stream_signature,
    verify_stream_token,
    verify_v3_signature,
)


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BW_", extra="ignore", hide_input_in_errors=True)
    gateway_origin: str
    gateway_token: SecretStr
    gateway_state_key: SecretStr
    redis_url: SecretStr
    plivo_auth_id: SecretStr = SecretStr("")
    plivo_auth_token: SecretStr = SecretStr("")
    plivo_from_number: SecretStr = SecretStr("")
    gateway_carrier: Literal["plivo", "twilio"] = "plivo"
    twilio_account_sid: SecretStr = SecretStr("")
    twilio_auth_token: SecretStr = SecretStr("")
    twilio_from_number: SecretStr = SecretStr("")
    engineering_recipient: SecretStr = SecretStr("")
    gateway_country: str = "IN"
    gateway_enabled: bool = False
    gateway_campaign_enabled: bool = False
    gateway_diagnostic_hold: bool = False
    gateway_stream_auth_mode: Literal["plivo_v3_and_token", "answer_bound_token"] = "plivo_v3_and_token"
    api_url: str
    runtime_token: SecretStr
    openai_api_key: SecretStr = SecretStr("")
    elevenlabs_api_key: SecretStr = SecretStr("")
    managed_closing_api_key: SecretStr = SecretStr("")
    voice_stt_model: str = "gpt-4o-mini-transcribe"
    voice_llm_model: str = "gpt-4.1-mini"
    voice_tts_model: str = "eleven_v4_turbo"
    voice_id: str = "pFZP5JQG7iQjIQuC4Bku"
    voice_direct_mode: str = "cascaded"
    voice_backend: Literal["cascaded", "elevenlabs"] = "cascaded"
    voice_speed: float = Field(default=1.0, ge=0.7, le=1.2)
    voice_stability: float = Field(default=0.5, ge=0, le=1)
    voice_similarity: float = Field(default=0.75, ge=0, le=1)
    voice_speaker_boost: bool = False
    voice_preemptive_generation: bool = False
    recording_notice: str = "This test call is recorded and uses fictional booking details."
    office_callback_number: str = ""
    release_id: str = "development"

    @model_validator(mode="after")
    def valid(self):
        configured_external_url(self.gateway_origin, "/health/ready")
        if not self.api_url.startswith("https://"):
            raise ValueError("Business API must use verified HTTPS")
        if len(self.gateway_token.get_secret_value()) < 32 or len(self.runtime_token.get_secret_value()) < 32:
            raise ValueError("Independent strong gateway/runtime credentials required")
        Fernet(self.gateway_state_key.get_secret_value().encode())
        if self.gateway_carrier == "twilio":
            import re

            if self.gateway_country != "GB" or not re.fullmatch(r"AC[0-9a-fA-F]{32}", self.twilio_account_sid.get_secret_value()) or not self.twilio_auth_token.get_secret_value():
                raise ValueError("Twilio requires a UK gateway and account credentials")
        elif not self.plivo_auth_id.get_secret_value() or not self.plivo_auth_token.get_secret_value():
            raise ValueError("Plivo account credentials are required")
        if self.gateway_country == "IN":
            if not self.plivo_from_number.get_secret_value().startswith("+91") or not self.engineering_recipient.get_secret_value().startswith("+91") or self.gateway_campaign_enabled:
                raise ValueError("India is an engineering-only route with one privately consented recipient")
        elif self.gateway_country == "GB":
            from brightwater.policy import Rejected, uk_phone
            try:
                uk_phone((self.twilio_from_number if self.gateway_carrier == "twilio" else self.plivo_from_number).get_secret_value())
            except Rejected:
                raise ValueError("Configure an approved real UK caller ID") from None
            if self.voice_backend != "elevenlabs":
                raise ValueError("Customer campaigns require the native ElevenLabs pipeline")
        else:
            raise ValueError("Unsupported carrier country")
        from brightwater.voice_pipeline import DirectVoiceOptions
        if self.voice_backend == "cascaded":
            DirectVoiceOptions.from_settings(self)
        if self.voice_backend == "cascaded" and self.voice_direct_mode != "cascaded":
            raise ValueError("This gateway requires the qualified timestamp-bearing cascaded pipeline")
        return self


class Outbound(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    call_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    session_token: SecretStr
    phone: SecretStr
    purpose: str
    max_seconds: int = Field(default=ATTENDED_CALL_MAX_SECONDS, ge=30, le=ATTENDED_CALL_MAX_SECONDS)


class StopCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    polite: bool = False
    closing_message: SecretStr | None = Field(default=None, min_length=1, max_length=400)


class State:
    def __init__(self, redis, cipher):
        self.redis, self.cipher = redis, cipher

    async def get(self, sid):
        raw = await self.redis.get("voice:session:" + sid)
        return json.loads(self.cipher.decrypt(raw)) if raw else None

    async def put(self, sid, value):
        await self.redis.set("voice:session:" + sid, self.cipher.encrypt(json.dumps(value).encode()), ex=86400)


def answer_xml(cfg, sid, token, max_seconds=ATTENDED_CALL_MAX_SECONDS):
    response = Element("Response")
    SubElement(response, "Record", {"recordSession": "true", "redirect": "false",
        "fileFormat": "wav", "recordChannelType": "stereo", "maxLength": str(max_seconds),
        "action": cfg.gateway_origin + "/plivo/recording-start/" + sid, "method": "POST",
        "callbackUrl": cfg.gateway_origin + "/plivo/recording/" + sid, "callbackMethod": "POST"})
    stream = SubElement(response, "Stream", {"bidirectional": "true", "keepCallAlive": "true", "contentType": "audio/x-mulaw;rate=8000"})
    stream.text = cfg.gateway_origin.replace("https://", "wss://", 1) + "/plivo/media/" + sid + "?token=" + token
    if cfg.gateway_diagnostic_hold:
        SubElement(response, "Speak").text = "The test connection needs a moment. Please hold while we connect the assistant."
        SubElement(response, "Wait", {"length": "180"})
    return tostring(response, encoding="utf-8", xml_declaration=True)


async def confirmed_recording(redis, sid, timeout=10):
    async def wait():
        while True:
            identifier = await redis.get("voice:recording-id:" + sid)
            if identifier:
                return identifier.decode()
            await asyncio.sleep(.1)
    return await asyncio.wait_for(wait(), timeout)


def speech_timing_sample(message):
    """Numeric stage timings only. No transcript, token or account identifiers."""
    metrics = getattr(message, "metrics", None) or {}
    sample = {"metric_type": "speech_timing", "unit": "seconds", "observed_at": time.time()}
    for key in ("e2e_latency", "llm_node_ttft", "tts_node_ttfb", "playback_latency", "end_of_turn_delay", "transcription_delay", "on_user_turn_completed_delay"):
        value = metrics.get(key)
        if type(value) in {int, float} and math.isfinite(value) and value >= 0:
            sample[key] = value
    return sample if len(sample) > 3 else None


async def record_speech_timing(redis, sid, message):
    sample = speech_timing_sample(message)
    if sample is not None:
        await store_latency_sample(redis, sid, sample)


def latency_sample(metrics):
    kind = getattr(metrics, "type", None)
    if kind not in {"llm_metrics", "eou_metrics", "tts_metrics", "stt_metrics"}:
        return None
    sample = {"metric_type": kind, "unit": "seconds", "observed_at": time.time()}
    for key in ("duration", "ttft", "ttfb", "end_of_utterance_delay", "transcription_delay",
                "on_user_turn_completed_delay", "audio_duration"):
        value = getattr(metrics, key, None)
        if type(value) in {float, int} and math.isfinite(value) and value >= 0:
            sample[key] = value
    return sample


async def record_latency(redis, sid, metrics):
    sample = latency_sample(metrics)
    if sample is None:
        return
    await store_latency_sample(redis, sid, sample)


async def store_latency_sample(redis, sid, sample):
    # Optional telemetry is local/bounded and cannot fail a customer's call.
    with contextlib.suppress(Exception):
        pipe = redis.pipeline()
        key = "voice:latency:" + sid
        pipe.rpush(key, json.dumps(sample))
        pipe.ltrim(key, -256, -1)
        pipe.expire(key, 86400)
        await asyncio.wait_for(pipe.execute(), timeout=1)


async def trusted_form(request, cfg):
    if cfg.gateway_carrier != "plivo":
        raise HTTPException(404)
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413)
    try:
        pairs = parse_qsl(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=256)
    except (ValueError, UnicodeError):
        raise HTTPException(400) from None
    url = configured_external_url(cfg.gateway_origin, request.url.path, request.url.query)
    if not verify_v3_signature(method="POST", external_url=url,
        nonce=request.headers.get("x-plivo-signature-v3-nonce"),
        signatures=request.headers.getlist("x-plivo-signature-v3"),
        auth_tokens=[cfg.plivo_auth_token.get_secret_value()], params=pairs):
        raise HTTPException(403)
    # Security-sensitive parameters may not be ambiguously repeated.
    if len({k for k, _ in pairs}) != len(pairs):
        raise HTTPException(400)
    return dict(pairs)


def validate_bound_form(data, state, cfg):
    if data.get("To", "").lstrip("+") != state["phone"].lstrip("+"):
        raise HTTPException(403)
    if data.get("From", "").lstrip("+") != cfg.plivo_from_number.get_secret_value().lstrip("+"):
        raise HTTPException(403)
    call_uuid = data.get("CallUUID", "")
    if not call_uuid or len(call_uuid) > 100:
        raise HTTPException(400)
    if state.get("call_uuid") and state["call_uuid"] != call_uuid:
        raise HTTPException(403)
    if state.get("request_uuid") and data.get("RequestUUID") != state["request_uuid"]:
        raise HTTPException(403)
    return call_uuid


def to_ogg(content):
    import av
    output = io.BytesIO()
    with av.open(io.BytesIO(content)) as source, av.open(output, mode="w", format="ogg") as target:
        stream = target.add_stream("libopus", rate=48000)
        stream.layout = "stereo"
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
        for frame in source.decode(audio=0):
            for converted in resampler.resample(frame):
                for packet in stream.encode(converted):
                    target.mux(packet)
        for converted in resampler.resample(None):
            for packet in stream.encode(converted):
                target.mux(packet)
        for packet in stream.encode(None):
            target.mux(packet)
    return output.getvalue()


def create_app(cfg):
    @asynccontextmanager
    async def lifespan(app):
        from livekit.local_inference import init_eot, init_vad
        if cfg.voice_backend == "cascaded":
            await asyncio.to_thread(init_eot)
        await asyncio.to_thread(init_vad)
        app.state.redis = Redis.from_url(cfg.redis_url.get_secret_value())
        app.state.store = State(app.state.redis, Fernet(cfg.gateway_state_key.get_secret_value().encode()))
        app.state.http = httpx.AsyncClient(follow_redirects=False)
        if cfg.gateway_carrier == "twilio":
            from brightwater.twilio_voice import TwilioClient

            app.state.carrier = TwilioClient(app.state.http, cfg.twilio_account_sid.get_secret_value(),
                cfg.twilio_auth_token.get_secret_value(), cfg.gateway_origin)
        else:
            app.state.carrier = PlivoClient(app.state.http, PlivoCredentials(
                cfg.plivo_auth_id.get_secret_value(), cfg.plivo_auth_token.get_secret_value()))
        app.state.tasks = set()
        app.state.active_bridges = {}
        # Recover jobs held by a process that stopped before acknowledging them.
        while await app.state.redis.rpoplpush("voice:recordings-processing", "voice:recordings"):
            pass
        task = asyncio.create_task(recording_worker(app))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            for pending in app.state.tasks:
                pending.cancel()
            await asyncio.gather(*app.state.tasks, return_exceptions=True)
            await app.state.http.aclose()
            await app.state.redis.aclose()

    app = FastAPI(title="Brightwater voice gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    async def event(context, kind, payload=None, event_id=None, occurred_at=None):
        from datetime import UTC, datetime
        result = await app.state.http.post(cfg.api_url + "/internal/calls/" + context["call_id"] + "/events",
            headers={"Authorization": "Bearer " + cfg.runtime_token.get_secret_value()},
            json={"provider_event_id": event_id or secrets.token_hex(16), "kind": kind,
                "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(), "payload": payload or {}}, timeout=8)
        result.raise_for_status()

    @app.get("/health/ready")
    async def ready():
        await app.state.redis.ping()
        return {"status": "ready", "region": cfg.gateway_country, "enabled": cfg.gateway_enabled, "voice_backend": cfg.voice_backend, "release_id": cfg.release_id}

    @app.post("/v1/stop")
    async def stop(body: StopCall, authorization: str | None = Header(default=None)):
        if not authorization or not secrets.compare_digest(authorization, "Bearer " + cfg.gateway_token.get_secret_value()):
            raise HTTPException(401)
        # Resolve the carrier ID entirely from the existing, authenticated session.
        # A model or caller cannot supply a phone number or a carrier CallUUID.
        sid = await app.state.redis.get("voice:admission:" + body.call_id)
        context = await app.state.store.get(sid.decode()) if sid else None
        if not context or context.get("call_id") != body.call_id:
            raise HTTPException(404)
        if context.get("status") == "ended":
            return {"stopped": True, "already_ended": True}
        if await app.state.redis.get("voice:active") != body.call_id.encode() or not context.get("call_uuid") or not context.get("answer_verified"):
            raise HTTPException(409)
        bridge = getattr(app.state, 'active_bridges', {}).get(body.call_id) if body.polite or body.closing_message else None
        if not await app.state.redis.set("voice:stop:" + body.call_id, "requested", nx=True, ex=86400):
            return {"stopped": False, "already_requested": True}
        if bridge is not None:
            bridge.closing_message = body.closing_message.get_secret_value() if body.closing_message else None
            bridge.boundary_requested.set()
            return {'stopped': False, 'polite_closing_requested': True}
        try:
            await app.state.carrier.hangup(context["call_uuid"])
        except Exception:
            # Do not automatically repeat an uncertain carrier operation.
            raise HTTPException(502, "Stop acknowledgement uncertain; reconcile the existing call") from None
        return {"stopped": True}

    async def save_request_uuid(sid, identifier):
        current = await app.state.store.get(sid)
        if current.get("request_uuid") not in (None, identifier):
            raise RuntimeError("Carrier request identity conflict")
        current.update(request_uuid=identifier)
        await app.state.store.put(sid, current)

    @app.post("/v1/outbound", status_code=202)
    async def outbound(body: Outbound, authorization: str | None = Header(default=None)):
        if not authorization or not secrets.compare_digest(authorization, "Bearer " + cfg.gateway_token.get_secret_value()):
            raise HTTPException(401)
        if not cfg.gateway_enabled:
            raise HTTPException(403)
        if body.purpose == "engineering":
            if cfg.gateway_country != "IN" or body.phone.get_secret_value() != cfg.engineering_recipient.get_secret_value():
                raise HTTPException(403)
        elif body.purpose == "campaign":
            if cfg.gateway_country != "GB" or not cfg.gateway_campaign_enabled or body.max_seconds > 900:
                raise HTTPException(403)
            from brightwater.policy import Rejected, uk_phone
            try:
                uk_phone(body.phone.get_secret_value())
            except Rejected:
                raise HTTPException(403) from None
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                approved = await client.post(cfg.api_url.rstrip("/") + "/internal/campaign/admission",
                    headers={"Authorization": "Bearer " + cfg.runtime_token.get_secret_value()},
                    json={"call_id": body.call_id, "session_token": body.session_token.get_secret_value(), "phone": body.phone.get_secret_value()})
                if approved.status_code != 200 or approved.json().get("admitted") is not True or approved.json().get("call_id") != body.call_id:
                    raise HTTPException(403)
        else:
            raise HTTPException(403)
        # Durable single-call claim; never repeat a possibly accepted carrier POST.
        old = await app.state.redis.get("voice:admission:" + body.call_id)
        if old:
            context = await app.state.store.get(old.decode())
            if context and context.get("request_uuid"):
                return {"request_uuid": context["request_uuid"], "replayed": True}
            raise HTTPException(409, "Existing request requires reconciliation")
        sid = secrets.token_hex(24)
        if not await app.state.redis.set("voice:active", body.call_id, nx=True, ex=body.max_seconds + 300):
            raise HTTPException(409, "Another call is active or uncertain")
        if not await app.state.redis.set("voice:admission:" + body.call_id, sid, nx=True, ex=86400):
            raise HTTPException(409)
        context = {"sid": sid, "call_id": body.call_id, "purpose": body.purpose, "phone": body.phone.get_secret_value(),
            "session_token": body.session_token.get_secret_value(), "max_seconds": body.max_seconds,
            "created": time.time(), "status": "initiating"}
        await app.state.store.put(sid, context)
        try:
            if cfg.gateway_carrier == "twilio":
                identifier = await app.state.carrier.make_call(sid=sid, from_number=cfg.twilio_from_number.get_secret_value(),
                    to_number=context["phone"], max_seconds=body.max_seconds)
                async with app.state.redis.lock("voice:twilio-state:" + sid, timeout=10, blocking_timeout=2):
                    await save_request_uuid(sid, identifier)
            else:
                identifier = await app.state.carrier.make_call(from_number=cfg.plivo_from_number.get_secret_value(),
                    to_number=context["phone"], answer_url=cfg.gateway_origin + "/plivo/answer/" + sid,
                    hangup_url=cfg.gateway_origin + "/plivo/status/" + sid, max_seconds=body.max_seconds)
                await save_request_uuid(sid, identifier)
            return {"request_uuid": identifier}
        except Exception:
            raise HTTPException(502, "Carrier acknowledgement uncertain; do not redial") from None

    @app.post("/plivo/answer/{sid}")
    async def answer(sid: str, request: Request):
        data = await trusted_form(request, cfg)
        context = await app.state.store.get(sid)
        if not context or time.time() - context["created"] > 90:
            raise HTTPException(410)
        actual = validate_bound_form(data, context, cfg)
        if context.get("status") == "ended":
            raise HTTPException(410)
        if not await app.state.redis.set("voice:bind:" + sid, actual, nx=True, ex=86400):
            bound = await app.state.redis.get("voice:bind:" + sid)
            if bound.decode() != actual:
                raise HTTPException(403)
        context.update(call_uuid=actual, request_uuid=data.get("RequestUUID"), status="answered", answer_verified=True, recording_requested=True, answer_callback_at=time.time())
        await app.state.store.put(sid, context)
        token = create_stream_token(secret=cfg.gateway_token.get_secret_value(), call_id=context["call_id"], call_uuid=actual, ttl_seconds=120)
        return Response(answer_xml(cfg, sid, token, context["max_seconds"]), media_type="application/xml")

    @app.post("/plivo/status/{sid}")
    async def status(sid: str, request: Request):
        data = await trusted_form(request, cfg)
        context = await app.state.store.get(sid)
        if not context:
            raise HTTPException(404)
        # A no-answer may have no previous stream, but signed identity still binds.
        actual = validate_bound_form(data, context, cfg)
        context.update(call_uuid=actual, status="ended", hangup_cause=data.get("HangupCauseName", "unknown"))
        await app.state.store.put(sid, context)
        await event(context, "ended", {"carrier_call_uuid": actual, "hangup_cause": context["hangup_cause"],
            "source": "signed_plivo_status", "carrier_answered": context.get("answer_verified") is True}, event_id="plivo-ended:" + actual)
        await app.state.redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end return 0", 1, "voice:active", context["call_id"])
        return {"accepted": True}

    @app.post("/plivo/recording-start/{sid}")
    async def recording_start(sid: str, request: Request):
        from uuid import UUID
        data = await trusted_form(request, cfg)
        context = await app.state.store.get(sid)
        if not context or not context.get("recording_requested") or context.get("answer_verified") is not True or data.get("CallUUID") != context.get("call_uuid"):
            raise HTTPException(403)
        identifier = data.get("RecordingID", "")
        try:
            UUID(identifier)
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400) from None
        if str(data.get("RecordingDuration")) != "-1":
            raise HTTPException(400)
        await app.state.redis.set("voice:recording-id:" + sid, identifier, nx=True, ex=86400)
        if await app.state.redis.get("voice:recording-id:" + sid) != identifier.encode():
            raise HTTPException(409)
        return Response(b"<Response/>", media_type="application/xml")

    @app.post("/plivo/recording/{sid}")
    async def recording(sid: str, request: Request):
        data = await trusted_form(request, cfg)
        context = await app.state.store.get(sid)
        if not context or data.get("CallUUID") != context.get("call_uuid"):
            raise HTTPException(403)
        identifier = await app.state.redis.get("voice:recording-id:" + sid)
        if not identifier or data.get("RecordingID") != identifier.decode():
            raise HTTPException(403)
        if await app.state.redis.set("voice:recording-job:" + sid, "queued", nx=True, ex=86400):
            await app.state.redis.rpush("voice:recordings", sid)
        return {"accepted": True}

    @app.websocket("/plivo/media/{sid}")
    async def media(ws: WebSocket, sid: str):
        if cfg.gateway_carrier != "plivo":
            await ws.close(code=1008)
            return
        context = await app.state.store.get(sid)
        url = configured_external_url(cfg.gateway_origin, ws.url.path, ws.url.query)
        signature_mode = verify_stream_signature(external_url=url,
            nonce=ws.headers.get("x-plivo-signature-v3-nonce"),
            signatures=ws.headers.getlist("x-plivo-signature-v3") + ws.headers.getlist("x-plivo-signature-ma-v3"),
            auth_tokens=[cfg.plivo_auth_token.get_secret_value()])
        valid = bool(signature_mode)
        claims = verify_stream_token(token=ws.query_params.get("token", ""), secret=cfg.gateway_token.get_secret_value(),
            call_id=context["call_id"] if context else "", call_uuid=context.get("call_uuid", "") if context else "")
        # Explicit capability authentication: this token is minted/delivered
        # only by a V3-verified, destination-bound answer callback. It binds both
        # IDs, expires absolutely, and is consumed once before any audio. The
        # configured mode is never caller-selectable or an automatic fallback.
        answer_bound = bool(context and context.get("answer_verified") is True)
        carrier_gate = valid if cfg.gateway_stream_auth_mode == "plivo_v3_and_token" else answer_bound
        if context and cfg.gateway_diagnostic_hold and not valid:
            with contextlib.suppress(Exception):
                forensic = {"at": time.time(), "call_id": context["call_id"], "url": url,
                    "nonce": ws.headers.getlist("x-plivo-signature-v3-nonce"),
                    "v3": ws.headers.getlist("x-plivo-signature-v3"),
                    "ma_v3": ws.headers.getlist("x-plivo-signature-ma-v3")}
                await app.state.redis.set("voice:handshake-forensic:" + sid,
                    app.state.store.cipher.encrypt(json.dumps(forensic).encode()), ex=600)
        if not context or not carrier_gate or not claims or context.get("status") != "answered":
            # Retain only validation flags; never log URI tokens/signature values.
            if context:
                with contextlib.suppress(Exception):
                    forensic = {"at": time.time(), "call_id": context["call_id"], "url": url,
                        "nonce": ws.headers.getlist("x-plivo-signature-v3-nonce"),
                        "v3": ws.headers.getlist("x-plivo-signature-v3"),
                        "ma_v3": ws.headers.getlist("x-plivo-signature-ma-v3")}
                    await app.state.redis.set("voice:handshake-forensic:" + sid,
                        app.state.store.cipher.encrypt(json.dumps(forensic).encode()), ex=600)
                    await app.state.redis.rpush("voice:handshake-review", json.dumps({
                        "at": time.time(), "call_id": context.get("call_id") if context else None,
                        "context_present": bool(context), "context_status": context.get("status") if context else None,
                        "v3_header_present": bool(ws.headers.get("x-plivo-signature-v3")),
                        "ma_v3_header_present": bool(ws.headers.get("x-plivo-signature-ma-v3")),
                        "nonce_present": bool(ws.headers.get("x-plivo-signature-v3-nonce")),
                        "signature_valid": valid, "application_token_valid": bool(claims)}))
                    await app.state.redis.ltrim("voice:handshake-review", -64, -1)
            await ws.close(code=1008)
            return
        if not await app.state.redis.set("voice:media:" + sid, claims.session_id, nx=True, ex=86400):
            await ws.close(code=1008)
            return
        await ws.accept()
        await app.state.redis.rpush("voice:handshake-accepted", json.dumps({"call_id": context["call_id"], "signature_mode": signature_mode, "stream_auth_mode": cfg.gateway_stream_auth_mode, "carrier_signature_valid": valid, "answer_verified": answer_bound, "at": time.time()}))
        await app.state.redis.ltrim("voice:handshake-accepted", -64, -1)
        task = asyncio.current_task()
        app.state.tasks.add(task)
        try:
            await run_voice(app, ws, context, cfg, event)
        finally:
            app.state.tasks.discard(task)

    async def recording_worker(app):
        while True:
            job = await app.state.redis.blmove("voice:recordings", "voice:recordings-processing", 2)
            if not job:
                continue
            sid = job.decode()
            cancelled = False
            try:
                context = await app.state.store.get(sid)
                identifier = await app.state.redis.get("voice:recording-id:" + sid)
                if cfg.gateway_carrier == "twilio":
                    bound = await app.state.redis.get("voice:bind:" + sid)
                    content = await app.state.carrier.recording(identifier.decode(), bound.decode(), MAX_CARRIER_RECORDING_BYTES)
                else:
                    metadata = await app.state.carrier.recording_metadata(identifier.decode(), expected_call_uuid=context["call_uuid"])
                    url = metadata.get("recording_url", "")
                    host = urlparse(url)
                    if host.scheme != "https" or not host.hostname or not host.hostname.endswith((".plivo.com", ".amazonaws.com")) or host.username or host.password:
                        raise ValueError("Unexpected provider recording location")
                    content = bytearray()
                    async with app.state.http.stream("GET", url, timeout=30) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_CARRIER_RECORDING_BYTES:
                                raise ValueError("Recording size bound exceeded")
                ogg = await asyncio.to_thread(to_ogg, bytes(content))
                result = await app.state.http.post(cfg.api_url + "/internal/calls/" + context["call_id"] + "/recording",
                    content=ogg, headers={"Authorization": "Bearer " + cfg.runtime_token.get_secret_value(), "Content-Type": "audio/ogg"}, timeout=30)
                result.raise_for_status()
                await app.state.redis.set("voice:recording-job:" + sid, "stored", ex=86400)
            except asyncio.CancelledError:
                cancelled = True
                raise
            except Exception:
                await app.state.redis.set("voice:recording-job:" + sid, "failed-review-required", ex=86400)
                await app.state.redis.rpush("voice:recordings-failed", sid)
            finally:
                if not cancelled:
                    await app.state.redis.lrem("voice:recordings-processing", 1, job)

    if cfg.gateway_carrier == "twilio":
        from brightwater.twilio_voice import install_twilio

        install_twilio(app, cfg, event, run_voice)
    return app


async def run_voice(app, ws, context, cfg, event, *, account_id=None):
    from livekit.agents.utils import http_context

    from brightwater.plivo_audio import AudioTransportError, PlivoAudioTransport
    from brightwater.voice_agent import BrightwaterAgent
    from brightwater.voice_pipeline import build_voice_session
    async def verify_start(start):
        try:
            await app.state.carrier.stream_metadata(context["call_uuid"], start["streamId"])
            return True
        except (httpx.HTTPError, ValueError, KeyError):
            return False

    transport = PlivoAudioTransport(ws, expected_call_id=context["call_uuid"],
        expected_account_id=account_id or cfg.plivo_auth_id.get_secret_value(), verify_start=None if account_id else verify_start,
        startup_preroll=True)
    done = asyncio.Event()
    pending = set()
    metric_tasks = set()
    carrier = app.state.carrier

    class CarrierRoom:
        async def disconnect(self):
            done.set()
            await carrier.hangup(context["call_uuid"])

    async def receiver():
        initial_packets = []
        try:
            while not transport.is_closed:
                raw = await ws.receive_text()
                if len(raw) > 65536:
                    raise ValueError("Media message bound exceeded")
                if len(initial_packets) < 3:
                    initial_packets.append(raw)
                try:
                    await transport.handle_message(raw)
                except AudioTransportError:
                    # Preserve the precise authenticated wire event for a local
                    # regression replay. No plaintext packet/audio enters logs.
                    with contextlib.suppress(Exception):
                        evidence = {"call_id": context["call_id"], "packet": raw, "initial_packets": initial_packets,
                            "validation_stage": transport.input_failure_stage,
                            "queued_frames": transport._input.qsize(), "queued_bytes": transport._input_bytes,
                            "expected_call_uuid": context["call_uuid"],
                            "expected_account_id": account_id or cfg.plivo_auth_id.get_secret_value(),
                            "codec": transport.codec, "failure_reason": transport.failure_reason}
                        await app.state.redis.set("voice:packet-failure:" + context["sid"],
                            app.state.store.cipher.encrypt(json.dumps(evidence).encode()), ex=600)
                    raise
        except (WebSocketDisconnect, ValueError):
            await transport.aclose()
        finally:
            done.set()

    startup_timing = {"media_handler_at": time.time()}
    if context.get("answer_callback_at") is not None:
        startup_timing["answer_callback_at"] = context["answer_callback_at"]
    context["startup_timing"] = startup_timing
    session = None
    stage = "media_start"
    diagnostic_hold = False
    await transport.start()
    receive = asyncio.create_task(receiver())
    try:
        await transport.wait_ready()
        startup_timing["authenticated_stream_ready_at"] = time.time()
        # Carrier duplex recording starts before any agent notice/account speech.
        stage = "carrier_recording_start"
        recording_id = await confirmed_recording(app.state.redis, context["sid"])
        context["recording_id"] = recording_id
        startup_timing["recording_confirmed_at"] = time.time()
        await app.state.store.put(context["sid"], context)
        stage = "connected_audit"
        await event(context, "connected", {"carrier_call_uuid": context["call_uuid"], "recording_id": recording_id}, event_id=cfg.gateway_carrier + "-connected:" + context["call_uuid"])
        startup_timing["connected_audit_completed_at"] = time.time()
        if cfg.voice_backend == "elevenlabs":
            from brightwater.managed.plivo import run_managed_phone
            stage = "managed_conversation"
            await run_managed_phone(app, context, cfg, transport, event)
            return
        async with http_context.open(), httpx.AsyncClient(base_url=cfg.api_url, timeout=8) as client:
            agent = BrightwaterAgent(SimpleNamespace(room=CarrierRoom()), context["call_id"], context["session_token"], client, cfg=cfg, notice_required=True)
            stage = "customer_context"
            details = await agent.request("GET", "/runtime/context")
            await agent.configure_identity(details["customer_display_name"], purpose=details.get("purpose", "campaign"))
            session = build_voice_session(cfg)
            session.input.audio, session.output.audio = transport.audio_input, transport.audio_output

            def track(task):
                pending.add(task)
                def finished(result):
                    if not result.cancelled() and result.exception() is not None:
                        done.set()  # Lost audit capture forbids continuing this call.
                task.add_done_callback(finished)

            def capture(kind, payload):
                track(asyncio.create_task(agent.event(kind, payload)))

            @session.on("user_state_changed")
            def user_state(change):
                if change.new_state == "speaking":
                    agent.turns.begin(started_at=change.created_at)
                elif change.new_state == "listening":
                    agent.turns.end(stopped_at=change.created_at)
                capture("turn_state", {"speaker": "user", "state": change.new_state, "server_monotonic": time.monotonic()})

            @session.on("agent_state_changed")
            def agent_state(change):
                capture("turn_state", {"speaker": "agent", "state": change.new_state, "server_monotonic": time.monotonic()})

            @session.on("user_interruption_detected")
            def interruption(change):
                capture("interruption", {"source": "local_vad", "server_monotonic": time.monotonic()})

            @session.on("error")
            def session_error(failure):
                if not getattr(failure.error, "recoverable", False):
                    capture("failed", {"source": "unrecoverable_voice_provider_error"})
                    done.set()

            @session.on("metrics_collected")
            def metrics_collected(change):
                if latency_sample(change.metrics) is None:
                    return
                task = asyncio.create_task(record_latency(app.state.redis, context["sid"], change.metrics))
                metric_tasks.add(task)
                task.add_done_callback(metric_tasks.discard)

            @session.on("conversation_item_added")
            def transcript(change):
                item = change.item
                if getattr(item, "role", None) == "user" and item.text_content:
                    track(asyncio.create_task(agent.capture_caller(item)))
                elif getattr(item, "role", None) == "assistant" and item.text_content:
                    task = asyncio.create_task(record_speech_timing(app.state.redis, context["sid"], item))
                    metric_tasks.add(task)
                    task.add_done_callback(metric_tasks.discard)
                    capture("agent_utterance", {"text": item.text_content, "interrupted": item.interrupted, "source": "plivo_agent_session"})

            stage = "agent_session_start"
            await session.start(agent)
            await agent.event("turn_state", {"source": "startup_preroll", "discarded_samples": transport.startup_discarded_samples,
                "sample_rate": 8000, "input_attached": transport.input_attached})
            stage = "opening_playback"
            await asyncio.wait_for(agent.deliver_opening(), timeout=40)
            stage = "conversation"
            watcher = asyncio.create_task(transport.wait_closed())
            waiter = asyncio.create_task(done.wait())
            finished, waiting = await asyncio.wait([watcher, waiter], timeout=context["max_seconds"], return_when=asyncio.FIRST_COMPLETED)
            for task in waiting:
                task.cancel()
            await asyncio.gather(*waiting, return_exceptions=True)
            if transport.failure_reason:
                session.interrupt()
                await agent.event("interruption", {"source": "media_transport_failure", "reason": transport.failure_reason})
            await session.aclose()
            await asyncio.gather(*(pending | agent.pending_writes), return_exceptions=False)
    except Exception as failure:
        # No invented result or blind retry. A recording/transport/provider failure
        # ends this carrier call and leaves an auditable failure event.
        diagnostic_hold = bool(cfg.gateway_diagnostic_hold and stage == "media_start" and isinstance(failure, AudioTransportError))
        with contextlib.suppress(Exception):
            await event(context, "turn_state" if diagnostic_hold else "failed", {
                "source": "voice_gateway_diagnostic_hold" if diagnostic_hold else "voice_gateway_failure",
                "stage": stage, "error_type": type(failure).__name__, "transport_reason": transport.failure_reason,
                "carrier_answered": context.get("answer_verified") is True})
    finally:
        done.set()
        if metric_tasks:
            await asyncio.gather(*metric_tasks, return_exceptions=True)
        if session:
            with contextlib.suppress(Exception):
                await session.aclose()
        receive.cancel()
        await asyncio.gather(receive, return_exceptions=True)
        await transport.aclose()
        if not diagnostic_hold:
            with contextlib.suppress(Exception):
                await carrier.hangup(context["call_uuid"])


def app_factory():
    return create_app(GatewaySettings())
