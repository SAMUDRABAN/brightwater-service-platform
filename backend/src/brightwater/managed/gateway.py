"""Native ElevenLabs server tools, scoped to an isolated evaluation diary."""
import hashlib
import json
import secrets
import time
from datetime import timedelta
from typing import Annotated

import httpx
from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS, ATTENDED_SESSION_TTL_SECONDS
from brightwater.config import settings
from brightwater.db import engine as office_engine
from brightwater.managed.engine import Conversation, create_evaluation, lab_engine, managed_error
from brightwater.policy import Rejected, now


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str
    text_only: bool = True


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    history: str = Field(max_length=2_000_000)
    text_only: bool
    arguments: dict = Field(default_factory=dict)


def broker():
    return Redis.from_url(settings().redis_url.get_secret_value(), socket_timeout=2, decode_responses=True)


def enabled():
    cfg = settings()
    if not cfg.managed_enabled or not cfg.managed_agent_id or not cfg.managed_api_key.get_secret_value() or len(cfg.managed_webhook_secret.get_secret_value()) < 32:
        raise Rejected("managed_disabled", "Managed candidate is not configured", 503)
    return cfg


def release_lease(redis, digest):
    redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end return 0", 1, "managed:lease", digest)


def reap_closed_phone_lease(redis):
    """An ended phone call must not block the next test for its maximum TTL."""
    digest = redis.get("managed:lease")
    raw = redis.get("managed:cap:" + digest) if digest else None
    state = json.loads(raw) if raw else {}
    if state.get("storage") != "phone":
        return
    with Session(office_engine()) as db:
        call = db.get(m.Call, state.get("id"))
        if call and call.purpose == "engineering" and call.state in {"finished", "failed"}:
            release_lease(redis, digest)


def conversation_from_history(call_id, text_only, raw, state):
    phone = state.get("storage") == "phone"
    if len(raw) > (2_000_000 if phone else 100_000):
        raise Rejected("invalid_provider_history", "Provider conversation evidence exceeds the limit", 422)
    try:
        history = json.loads(raw)
    except ValueError as error:
        raise Rejected("invalid_provider_history", "Provider conversation evidence is malformed", 422) from error
    if not isinstance(history, dict) or history.get("x-elevenlabs-history") is not True or not isinstance(history.get("entries"), list) or len(history["entries"]) > (10_000 if phone else 500):
        raise Rejected("invalid_provider_history", "Provider conversation evidence is absent", 422)
    conv = Conversation(call_id, text_only=text_only, trusted_phone=state.get("storage") == "phone")
    for entry in history["entries"]:
        if not isinstance(entry, dict):
            raise Rejected("invalid_provider_history", "Provider conversation evidence is malformed", 422)
        role, text = entry.get("role"), entry.get("message")
        if role not in {"user", "agent", "tool"}:
            raise Rejected("invalid_provider_history", "Unknown conversation role", 422)
        if text is None:
            continue
        if not isinstance(text, str) or len(text) > 8000:
            raise Rejected("invalid_provider_history", "Invalid conversation turn", 422)
        if role == "user":
            conv.user(text)
        elif role == "agent":
            conv.agent(text)
    conv.readbacks = state.get("readbacks", {})
    return conv


def closed_result(db, call_id, *, phone=False):
    call = db.get(m.Call, call_id)
    if call and call.purpose == ("engineering" if phone else "managed_evaluation") and call.state in {"finished", "failed"}:
        return {"finished": True, "outcome": call.outcome,
                "confirmed": bool(db.scalar(select(m.Booking.id).where(m.Booking.call_id == call.id, m.Booking.state == "confirmed"))),
                "instruction": "This session is complete. Its saved outcome remains valid. Do not reopen booking or claim a saved booking failed. Call end_call now."}
    return None


def save_transcript(db, call_id, conv):
    for index, turn in enumerate(conv.turns):
        key = "managed-turn:" + str(index)
        existing = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call_id, m.CallEvent.provider_event_id == key))
        if existing:
            # Provider may correct its in-progress transcript. Never treat a
            # changed earlier message as new consent or silently overwrite it.
            if existing.payload.get("text") != turn["text"]:
                raise Rejected("history_revised", "Earlier transcript changed; start a fresh evaluation")
        else:
            db.add(m.CallEvent(call_id=call_id, provider_event_id=key, kind="managed_transcript" if conv.trusted_phone else "user_utterance" if turn["role"] == "user" else "agent_utterance",
                              occurred_at=now(), payload={"source": "elevenlabs_native_history", "text": turn["text"], "speech_timing_verified": False}))
    db.flush()


def bind_conversation(db, call, conversation_id, *, phone=False):
    if not phone:
        call.provider_id = conversation_id
        return
    # provider_id is the Plivo RequestUUID for real calls. Never replace it
    # with an ElevenLabs conversation ID needed by a different reconciler.
    key = "managed-session:" + conversation_id
    if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
        db.add(m.CallEvent(call_id=call.id, provider_event_id=key, kind="managed_session", occurred_at=now(),
                          payload={"provider": "elevenlabs", "conversation_id": conversation_id}))


def install(app, operator, scoped_call):
    @app.get("/v1/managed/status", dependencies=[Depends(operator)])
    def status():
        cfg = settings()
        return {"enabled": cfg.managed_enabled, "provider": "ElevenLabs Agents", "voice": "Configured ElevenLabs voice / v4 Turbo",
                "phone_attached": False, "booking_audio_qualified": False,
                "phone_route_configured": cfg.managed_phone_enabled and bool(cfg.managed_phone_agent_id),
                "phone_route": "Plivo India engineering" if cfg.managed_phone_enabled else None,
                "evaluation_only": True, "duration_limit_seconds": ATTENDED_CALL_MAX_SECONDS if cfg.managed_phone_enabled else 180,
                "evaluation_duration_limit_seconds": 180}

    @app.get("/v1/managed/evaluations", dependencies=[Depends(operator)])
    def evaluations():
        enabled()
        with Session(lab_engine()) as db:
            calls = db.scalars(select(m.Call).where(m.Call.purpose == "managed_evaluation").order_by(m.Call.created_at.desc()).limit(30)).all()
            return [{"id": c.id, "customer_id": c.customer_id, "state": c.state, "outcome": c.outcome,
                     "identity_verified": c.identity_verified, "summary": c.summary,
                     "created_at": c.created_at.isoformat(), "purpose": c.purpose} for c in calls]

    @app.post("/v1/managed/sessions", dependencies=[Depends(operator)])
    def start(body: StartInput):
        cfg = enabled()
        token = secrets.token_urlsafe(40)
        digest = hashlib.sha256(token.encode()).hexdigest()
        redis = broker()
        reap_closed_phone_lease(redis)
        if not redis.set("managed:lease", digest, nx=True, ex=300):
            raise Rejected("managed_busy", "A managed evaluation is already active")
        try:
            day = "managed:daily:" + now().date().isoformat()
            count = redis.incr(day)
            redis.expire(day, 86400)
            if count > cfg.managed_evaluation_request_limit:
                raise Rejected("managed_daily_limit", "Daily engineering evaluation limit reached")
            with Session(lab_engine(), expire_on_commit=False) as db, db.begin():
                for old in db.scalars(select(m.Call).where(m.Call.purpose == "managed_evaluation", m.Call.state == "in_progress", m.Call.created_at < now() - timedelta(minutes=5))):
                    old.state, old.ended_at = "failed", now()
                value = create_evaluation(db, body.customer_id)
            with httpx.Client(timeout=15) as client:
                response = client.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                    headers={"xi-api-key": cfg.managed_api_key.get_secret_value()}, params={"agent_id": cfg.managed_agent_id})
                response.raise_for_status()
                signed_url = response.json()["signed_url"]
            # The provider URL is a short-lived browser capability, not an API key.
            redis.setex("managed:call:" + value["id"], 300, digest)
            redis.setex("managed:cap:" + digest, 300, json.dumps({**value, "text_only": body.text_only, "created_at": now().isoformat(), "conversation_id": None, "readbacks": {}}))
            return {**value, "token": token, "expires_in_seconds": 300, "signed_url": signed_url, "text_only": body.text_only}
        except Exception:
            release_lease(redis, digest)
            raise

    @app.post("/runtime/managed/session")
    def phone_session(call: Annotated[m.Call, Depends(scoped_call)],
                      x_brightwater_runtime: Annotated[str | None, Header()] = None):
        cfg = enabled()
        if not x_brightwater_runtime or not secrets.compare_digest(x_brightwater_runtime, cfg.runtime_token.get_secret_value()):
            raise Rejected("unauthorised", "Trusted gateway authentication required", 401)
        if not cfg.managed_phone_enabled or not cfg.managed_phone_agent_id or call.purpose != "engineering":
            raise Rejected("managed_phone_disabled", "The managed phone adapter is not enabled for this call", 403)
        with Session(office_engine()) as db:
            destination = db.get(m.Destination, call.destination_id)
            if not destination or destination.phone != cfg.engineering_recipient.get_secret_value() or not destination.enabled:
                raise Rejected("managed_phone_destination", "The carrier call must use the owned engineering destination", 403)
            name = db.get(m.Customer, call.customer_id).name
        token = secrets.token_urlsafe(40)
        digest = hashlib.sha256(token.encode()).hexdigest()
        redis = broker()
        reap_closed_phone_lease(redis)
        if not redis.set("managed:lease", digest, nx=True, ex=ATTENDED_SESSION_TTL_SECONDS):
            raise Rejected("managed_busy", "Another managed session is active")
        try:
            from brightwater.managed.startup import consume
            url_started = time.perf_counter()
            signed_url = consume(redis, call.id, cfg)
            prepared = signed_url is not None
            if signed_url is None:
                with httpx.Client(timeout=15) as client:
                    response = client.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                        headers={"xi-api-key": cfg.managed_api_key.get_secret_value()}, params={"agent_id": cfg.managed_phone_agent_id})
                    response.raise_for_status()
                    signed_url = response.json()["signed_url"]
            try:
                meta_key = "managed:phone-startup-meta:" + call.id
                meta = json.loads(redis.get(meta_key) or "{}")
                meta.update(prepared_url_hit=prepared, url_phase_seconds=time.perf_counter() - url_started)
                redis.setex(meta_key, 86400, json.dumps(meta))
            except Exception:
                pass  # Optional numeric timing never authorises or terminates a call.
            redis.setex("managed:cap:" + digest, ATTENDED_SESSION_TTL_SECONDS, json.dumps({"id": call.id, "storage": "phone",
                "text_only": False, "conversation_id": None, "readbacks": {}}))
            return {"token": token, "signed_url": signed_url, "customer_name": name,
                    "agent_id": cfg.managed_phone_agent_id}
        except Exception:
            release_lease(redis, digest)
            raise

    @app.post("/v1/managed/evaluations/{call_id}/close", dependencies=[Depends(operator)])
    def close(call_id: str):
        from brightwater.services import finalise
        with Session(lab_engine()) as db, db.begin():
            call = db.get(m.Call, call_id)
            if not call or call.purpose != "managed_evaluation":
                raise Rejected("not_found", "Evaluation not found", 404)
            if call.state == "in_progress":
                finalise(db, call, "Native managed evaluation ended. Outcome derives from saved business facts. No telephone call was made.")
        redis = broker()
        digest = redis.getdel("managed:call:" + call_id)
        if digest:
            redis.delete("managed:cap:" + digest)
            release_lease(redis, digest)
        return {"closed": True}

    @app.post("/v1/managed/tools/{name}")
    def tool(name: str, body: ToolInput,
             x_brightwater_provider: Annotated[str | None, Header()] = None,
             x_brightwater_session: Annotated[str | None, Header()] = None,
             x_brightwater_conversation: Annotated[str | None, Header()] = None):
        cfg = enabled()
        if not x_brightwater_provider or not secrets.compare_digest(x_brightwater_provider, cfg.managed_webhook_secret.get_secret_value()):
            raise Rejected("unauthorised", "Managed provider authentication required", 401)
        if not x_brightwater_session or not 40 <= len(x_brightwater_session) <= 100 or not x_brightwater_conversation or len(x_brightwater_conversation) > 160:
            raise Rejected("unauthorised", "A bound managed session is required", 401)
        digest = hashlib.sha256(x_brightwater_session.encode()).hexdigest()
        redis = broker()
        # Serialize native tools across API replicas, with fenced release.
        lock = redis.lock("managed:tool-lock:" + digest, timeout=20, blocking_timeout=5)
        if not lock.acquire():
            raise Rejected("managed_busy", "Previous tool still running")
        try:
            key = "managed:cap:" + digest
            raw = redis.get(key)
            if not raw:
                raise Rejected("unauthorised", "Managed session expired", 401)
            state = json.loads(raw)
            if state["conversation_id"] not in {None, x_brightwater_conversation} or body.text_only != state["text_only"]:
                raise Rejected("session_mismatch", "Provider conversation binding mismatch", 403)
            if redis.get("managed:lease") != digest:
                with Session(office_engine() if state.get("storage") == "phone" else lab_engine()) as db:
                    terminal = closed_result(db, state["id"], phone=state.get("storage") == "phone")
                if terminal and state["conversation_id"] == x_brightwater_conversation:
                    return terminal
                raise Rejected("unauthorised", "Managed session expired", 401)
            state["conversation_id"] = x_brightwater_conversation
            conv = conversation_from_history(state["id"], state["text_only"], body.history, state)
            if conv.trusted_phone and name in {"confirm_identity", "confirm_booking", "cancel_arrangement"} and conv.latest_user():
                from brightwater.managed.phone import wait_for_caller
                wait_for_caller(lambda: Session(office_engine()), state["id"], conv.latest_user()["text"])
            from brightwater.managed.semantic_runtime import snapshot
            from brightwater.managed.understanding import interpret
            with Session(office_engine() if conv.trusted_phone else lab_engine()) as evidence_db:
                current = evidence_db.get(m.Call, state["id"])
                semantic_snapshot = snapshot(evidence_db, current, conversation=conv,
                                             proposal_id=body.arguments.get("proposal_id"))
            conv.understanding = interpret(semantic_snapshot, redis=redis)
            conv.callback_previously_declined = semantic_snapshot['callback_previously_declined']
            conv.intent = conv.understanding.appointment_evidence() if semantic_snapshot['proposal_id'] else None
            # Tool identity derives from the provider-bound history and arguments,
            # never from a model-supplied request key or confirmation statement.
            operation = hashlib.sha256(json.dumps([name, body.arguments, conv.turns], sort_keys=True).encode()).hexdigest()
            with Session(office_engine() if conv.trusted_phone else lab_engine(), expire_on_commit=False) as db, db.begin():
                if conv.trusted_phone:
                    from brightwater.services import control_lock
                    control_lock(db)
                save_transcript(db, state["id"], conv)
                prior = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == state["id"], m.CallEvent.provider_event_id == "managed-tool:" + operation))
                terminal = closed_result(db, state["id"], phone=conv.trusted_phone)
                if terminal:
                    result = terminal
                elif prior:
                    result = prior.payload["result"]
                else:
                    from pydantic import ValidationError
                    try:
                        with db.begin_nested():
                            result = conv.execute(db, name, body.arguments, operation)
                    except Rejected as error:
                        result = managed_error(error, agreement_present=bool(conv.intent and conv.intent.decision == 'confirm'))
                    except ValidationError:
                        result = {"error": "invalid_parameters", "instruction": "Check the selected property, offer and tenant contacts. No booking was saved.", "confirmed": False, "saved": False}
                    if result.get("error") != "evidence_pending":
                        db.add(m.CallEvent(call_id=state["id"], provider_event_id="managed-tool:" + operation,
                                          kind="managed_tool_result", occurred_at=now(), payload={"name": name, "result": result}))
                call = db.get(m.Call, state["id"])
                bind_conversation(db, call, x_brightwater_conversation, phone=conv.trusted_phone)
            state["readbacks"] = conv.readbacks
            redis.set(key, json.dumps(state), keepttl=True)
            if conv.closed:
                release_lease(redis, digest)
            if conv.trusted_phone and result.get('stopped'):
                from brightwater.managed.semantic_runtime import stop_carrier
                stop_carrier(state['id'], polite=bool(result.get('boundary_reason')))
            return result
        finally:
            try:
                lock.release()
            except Exception:
                pass
