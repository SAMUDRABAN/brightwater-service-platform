import hashlib
import secrets
from datetime import timedelta
from importlib.metadata import version
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater import staff
from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS, ATTENDED_SESSION_TTL_SECONDS
from brightwater.config import settings
from brightwater.db import get_db, session
from brightwater.knowledge import lookup
from brightwater.media import MAX_RECORDING_BYTES, read_recording, store_recording
from brightwater.policy import CO_ADVICE, GAS_ADVICE, SERVICES, UK, Rejected, now

app = FastAPI(title="Brightwater control plane", version=version("brightwater"), docs_url=None, redoc_url=None, openapi_url=None)
DB = Annotated[Session, Depends(get_db, scope="function")]


app.include_router(staff.router)


def operator(request: Request, db: DB, authorization: Annotated[str | None, Header()] = None):
    if authorization and secrets.compare_digest(authorization, "Bearer " + settings().operator_token.get_secret_value()):
        request.state.staff = None
        return
    user = staff.principal(db, authorization)
    request.state.staff = user
    if user.change_required:
        raise Rejected("password_change_required", "Change your initial password first", 403)
    path = request.url.path
    allowed = user.role == "admin" or (user.role == "engineer" and staff.engineer_allowed(request.method, path)) or (user.role == "office" and staff.office_allowed(request.method, path))
    if user.role == "engineer" and not user.engineer_id:
        raise Rejected("forbidden", "Engineer assignment is missing", 403)
    if not allowed:
        raise Rejected("forbidden", "Your role does not have access to this resource", 403)
    if request.method != "GET":
        staff.audit(db, user.username, request.method + " " + path[:120])


def runtime(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not secrets.compare_digest(authorization, "Bearer " + settings().runtime_token.get_secret_value()):
        raise Rejected("unauthorised", "Trusted runtime authentication required", 401)


def scoped_call(db: DB, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise Rejected("unauthorised", "Call-scoped credential required", 401)
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    call = db.scalar(select(m.Call).where(m.Call.session_token_hash == digest))
    max_age = ATTENDED_SESSION_TTL_SECONDS if call and call.purpose == "engineering" else 3600
    if not call or call.state != "in_progress" or now() - call.created_at > timedelta(seconds=max_age):
        raise Rejected("unauthorised", "Call session is absent, expired or closed", 401)
    return call


CALL = Annotated[m.Call, Depends(scoped_call)]
OPERATOR = [Depends(operator)]
RUNTIME = [Depends(runtime)]


def row(value, exclude=()):
    return {c.name: getattr(value, c.name) for c in value.__table__.columns if c.name not in exclude}


@app.exception_handler(Rejected)
async def rejected_handler(request, error):
    return JSONResponse(status_code=error.status, content={"error": error.code, "message": error.message})


@app.middleware("http")
async def response_controls(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(db: DB):
    db.execute(text("SELECT 1"))
    try:
        Redis.from_url(settings().redis_url.get_secret_value(), socket_timeout=1).ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "dependency": "broker"})
    return {"status": "ready", "environment": settings().environment, "dialing_enabled": settings().dialing_enabled}


@app.get("/metrics", dependencies=OPERATOR)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/customers", dependencies=OPERATOR)
def customers(db: DB):
    values = db.scalars(select(m.Customer).where(m.Customer.id != "ENGINEERING-SAMUDRA").order_by(m.Customer.name)).all()
    destinations = {d.customer_id: d for d in db.scalars(select(m.Destination))}
    suppressions = list(db.scalars(select(m.Suppression)))
    due = dict(db.execute(select(m.Property.customer_id, func.min(m.Obligation.due_date)).join(
        m.Obligation, m.Obligation.property_id == m.Property.id).where(m.Obligation.resolved.is_(False)).group_by(m.Property.customer_id)).all())
    properties = dict(db.execute(select(m.Property.customer_id, func.count()).group_by(m.Property.customer_id)).all())
    return [{"id": c.id, "name": c.name, "kind": c.kind, "not_before": c.not_before,
             "contact_blocked": c.contact_blocked,
             "suppressed": any(x.customer_id == c.id or x.phone in {c.source_phone, destinations[c.id].phone if c.id in destinations else ""} for x in suppressions),
             "destination_approved": bool(c.id in destinations and destinations[c.id].enabled),
             "next_due": due.get(c.id), "property_count": properties.get(c.id, 0)} for c in values]


@app.post("/v1/customers/{customer_id}/destination", dependencies=OPERATOR)
def destination(customer_id: str, body: s.DestinationInput, db: DB):
    value = svc.register_destination(db, customer_id, body.phone, body.consent_reference)
    return {"id": value.id, "enabled": value.enabled}


@app.post("/v1/calls", dependencies=OPERATOR, status_code=202)
def request_call(body: s.CallInput, db: DB):
    if not settings().dialing_enabled:
        raise Rejected("dialing_disabled", "Configure and approve the Plivo/LiveKit route before enabling real calls")
    control = db.get(m.Control, "dialing")
    if not control or not control.enabled:
        raise Rejected("kill_switch", "New calls are paused")
    value = svc.request_call(db, body.customer_id, body.request_key)
    return {"id": value.id, "state": value.state}


@app.get("/v1/engineering/status", dependencies=OPERATOR)
def engineering_status(db: DB):
    cfg = settings()
    rows = db.scalars(select(m.Call).where(m.Call.purpose == "engineering")).all()
    phone = cfg.engineering_recipient.get_secret_value()
    control = db.get(m.Control, "engineering")
    return {"enabled": cfg.engineering_enabled and (not control or control.enabled), "recipient": ("ending " + phone[-4:]) if phone else "not configured",
        "limit": cfg.engineering_call_limit, "used": len(rows), "remaining": max(0, cfg.engineering_call_limit - len(rows)),
        "active": any(c.state in svc.ACTIVE for c in rows), "duration_limit_seconds": ATTENDED_CALL_MAX_SECONDS}


@app.post("/v1/engineering/calls", dependencies=OPERATOR, status_code=202)
async def engineering_call(body: s.EngineeringCallInput, background_tasks: BackgroundTasks):
    from brightwater.engineering import prepare_engineering
    cfg = settings()
    if not cfg.engineering_enabled:
        raise Rejected("engineering_disabled", "Attended engineering calling is not enabled")
    # Check this container's real route before creating durable dial intent.
    # A failed readiness GET cannot have placed a telephone call.
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            probe = await client.get(cfg.voice_gateway_url + "/health/ready")
            probe.raise_for_status()
            evidence = probe.json()
            if evidence.get("status") != "ready" or evidence.get("enabled") is not True or evidence.get("region") != "IN":
                raise ValueError("Regional gateway is not admitted")
    except (httpx.HTTPError, ValueError):
        raise Rejected("voice_gateway_unavailable", "The regional voice service is not ready; no call was requested", 503) from None
    with session() as db, db.begin():
        value, token = prepare_engineering(db, cfg, body.request_key)
        call_id, state = value.id, value.state
    if token is None:
        return {"id": call_id, "state": state, "purpose": "engineering", "replayed": True}
    # The durable claim precedes the external request. A timeout is quarantined,
    # never retried as a second dial; gateway also deduplicates this stable ID.
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(cfg.voice_gateway_url + "/v1/outbound",
                headers={"Authorization": "Bearer " + cfg.voice_gateway_token.get_secret_value()},
                json={"call_id": call_id, "session_token": token,
                      "phone": cfg.engineering_recipient.get_secret_value(), "purpose": "engineering",
                      "max_seconds": ATTENDED_CALL_MAX_SECONDS})
            response.raise_for_status()
            provider_id = response.json()["request_uuid"]
        with session() as db, db.begin():
            call = db.get(m.Call, call_id)
            call.provider_id = provider_id
        from brightwater.managed.startup import prepare
        background_tasks.add_task(prepare, call_id)
        return {"id": call_id, "state": "dispatching", "purpose": "engineering"}
    except Exception:
        with session() as db, db.begin():
            call = db.get(m.Call, call_id)
            if call.state == "dispatching":
                call.state = "unknown"
                db.add(m.Followup(call_id=call.id, kind="internal_review", owner="Sarah", priority=1,
                    detail="Engineering provider initiation was not acknowledged. Reconcile this call; no automatic redial.", requested=False))
        return {"id": call_id, "state": "unknown", "purpose": "engineering"}


@app.post("/v1/control/pause", dependencies=OPERATOR)
def pause(db: DB):
    svc.control_lock(db)
    control = db.get(m.Control, "dialing")
    if control:
        control.enabled = False
    engineering = db.get(m.Control, "engineering")
    if engineering:
        engineering.enabled = False
    else:
        db.add(m.Control(key="engineering", enabled=False))
    return {"dialing_paused": True, "engineering_paused": True}


@app.get("/v1/calls", dependencies=OPERATOR)
def calls(db: DB):
    return [row(c, {"session_token_hash"}) for c in db.scalars(select(m.Call).order_by(m.Call.created_at.desc()).limit(100))]


@app.get("/v1/calls/{call_id}", dependencies=OPERATOR)
def call_detail(call_id: str, db: DB):
    from brightwater.arrangements import current
    value = db.get(m.Call, call_id)
    if not value:
        raise Rejected("not_found", "Call not found", 404)
    return {**row(value, {"session_token_hash"}), "customer_name": svc.customer(db, value.customer_id).name,
            "events": [row(e) for e in db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call_id).order_by(m.CallEvent.occurred_at))],
            "bookings": [row(b) for b in db.scalars(select(m.Booking).where(m.Booking.call_id == call_id))],
            "arrangement": current(db, value)}


@app.get("/v1/campaign/status", dependencies=OPERATOR)
def campaign_status(db: DB):
    from brightwater.campaign import status
    return status(db, settings())


@app.get("/v1/dashboard", dependencies=OPERATOR)
def dashboard(request: Request, db: DB):
    today = now().astimezone(UK).date()
    call_rows = db.scalars(select(m.Call).where(m.Call.purpose == "campaign")).all()
    booked_customers = set(db.scalars(select(m.Booking.customer_id).join(m.Call, m.Call.id == m.Booking.call_id).where(m.Booking.state == "confirmed", m.Call.purpose == "campaign")))
    contacted = {c.customer_id for c in call_rows if c.dispatched_at}
    reached = {c.customer_id for c in call_rows if c.conversation}
    customer_count = db.scalar(select(func.count()).select_from(m.Customer).where(m.Customer.id != "ENGINEERING-SAMUDRA"))
    followups = []
    for follow in db.scalars(select(m.Followup).where(m.Followup.resolved.is_(False)).order_by(m.Followup.priority, m.Followup.created_at)):
        call = db.get(m.Call, follow.call_id)
        followups.append({**row(follow), "customer_name": svc.customer(db, call.customer_id).name,
                          "summary": call.summary, "media_state": call.media_state, "purpose": call.purpose, "customer_id": call.customer_id})
    viewer = getattr(request.state, "staff", None)
    engineer_id = viewer.engineer_id if viewer and viewer.role == "engineer" else None
    appointments = []
    for booking, item, window, engineer, prop in db.execute(select(m.Booking, m.BookingItem, m.DiaryWindow, m.Engineer, m.Property).join(
        m.BookingItem, m.BookingItem.booking_id == m.Booking.id).join(
        m.DiaryWindow, m.DiaryWindow.id == m.BookingItem.window_id).join(
        m.Engineer, m.Engineer.id == m.DiaryWindow.engineer_id).join(
        m.Property, m.Property.id == m.BookingItem.property_id).where(m.Booking.state == "confirmed").order_by(m.DiaryWindow.day)):
        if engineer_id and engineer.id != engineer_id:
            continue
        appointments.append({"booking_id": booking.id, "created_yesterday": booking.created_at.astimezone(UK).date() == today - timedelta(days=1),
                             "day": window.day, "period": window.period, "engineer": engineer.name,
                             "address": prop.address, "service": item.service, "state": booking.state, "call_id": booking.call_id, "customer_id": booking.customer_id, "customer_name": svc.customer(db, booking.customer_id).name, "price_pence": item.price_pence, "purpose": db.get(m.Call, booking.call_id).purpose})
    capacity = db.execute(select(func.sum(m.DiaryWindow.capacity_minutes), func.sum(m.DiaryWindow.used_minutes))).one()
    if viewer and viewer.role == "engineer":
        return {"appointments": appointments, "viewer": staff.public(viewer)}
    return {"environment": settings().environment, "release_id": settings().release_id,
            "dialing_enabled": settings().dialing_enabled and bool(db.get(m.Control, "dialing") and db.get(m.Control, "dialing").enabled),
            "metrics": {"customers": customer_count, "called": len(contacted), "reached": len(reached),
                        "booked": len(booked_customers), "still_to_try": customer_count - len(contacted),
                        "attempts": sum(c.dispatched_at is not None for c in call_rows)},
            "followups": followups, "appointments": appointments,
            "diary": {"capacity_minutes": capacity[0] or 0, "used_minutes": capacity[1] or 0},
            "quality": {"status": "NOT EVALUATED", "voice_score": None, "conversation_score": None}}


@app.post("/internal/calls/{call_id}/events", dependencies=RUNTIME)
def events(call_id: str, body: s.EventInput, db: DB, background_tasks: BackgroundTasks):
    value = svc.record_event(db, call_id, body)
    if body.kind == "user_utterance" and body.payload.get("source") == "plivo_elevenlabs_observer":
        from brightwater.managed.semantic_runtime import prefetch
        background_tasks.add_task(prefetch, call_id, value.id)
    if (body.kind == 'agent_utterance' and body.payload.get('source') == 'plivo_elevenlabs_observer'
        or body.kind == 'turn_state' and body.payload.get('source') == 'managed_agent_prompt'):
        from brightwater.managed.semantic_runtime import prefetch_readback
        background_tasks.add_task(prefetch_readback, call_id, value.id)
    return {"event_id": value.id}


@app.post("/internal/campaign/admission", dependencies=RUNTIME)
def campaign_admission(body: s.CampaignAdmission, db: DB):
    from brightwater.campaign import configuration_issues
    cfg = settings()
    svc.control_lock(db)
    call = db.scalar(select(m.Call).where(m.Call.id == body.call_id).with_for_update())
    control = db.get(m.Control, "dialing")
    digest = hashlib.sha256(body.session_token.get_secret_value().encode()).hexdigest()
    if (not cfg.dialing_enabled or configuration_issues(cfg) or not control or not control.enabled
        or not call or call.purpose != "campaign" or call.state != "dispatching"
        or not call.session_token_hash or not secrets.compare_digest(call.session_token_hash, digest)
        or not call.dispatched_at or not timedelta(0) <= now() - call.dispatched_at <= timedelta(seconds=60)):
        raise Rejected("campaign_not_admitted", "No current approved campaign admission", 403)
    destination = db.get(m.Destination, call.destination_id)
    if not destination or destination.phone != body.phone.get_secret_value():
        raise Rejected("destination_mismatch", "The carrier destination must match the approved call", 403)
    svc.check_dial_policy(db, svc.customer(db, call.customer_id), destination, now(), exclude_call=call.id)
    return {"admitted": True, "purpose": "campaign", "call_id": call.id}


@app.get("/runtime/context")
def context(call: CALL, db: DB):
    return {"customer_display_name": svc.customer(db, call.customer_id).name,
            "identity_verified": call.identity_verified, "call_id": call.id, "purpose": call.purpose,
            "opening": "Hi, I'm Alex, Brightwater Plumbing & Heating's AI assistant."}


@app.get("/runtime/account")
def account(call: CALL, db: DB):
    return svc.account(db, call)


@app.get("/runtime/services")
def service_options(call: CALL):
    svc.verified(call)
    return SERVICES


@app.get("/runtime/knowledge")
def knowledge(call: CALL, query: str = Query(min_length=1, max_length=400)):
    return lookup(query)


@app.post("/runtime/availability")
def availability(body: s.AvailabilityInput, call: CALL, db: DB):
    return svc.availability(db, call, body.items, preferred_day=body.preferred_day, preferred_period=body.preferred_period, engineer_id=body.engineer_id, after_day=body.after_day, same_day=body.same_day)


@app.post("/runtime/bookings/prepare")
def prepare(body: s.PrepareInput, call: CALL, db: DB):
    return row(svc.prepare(db, call, body.offer_id, body.tenants))


@app.post("/runtime/bookings/commit")
def commit(body: s.CommitInput, call: CALL, db: DB):
    return row(svc.commit(db, call.id, body.proposal_id, body.confirmation_event_id))


@app.get("/runtime/operations/{operation_id}")
def operation(operation_id: str, call: CALL, db: DB):
    proposal = db.scalar(select(m.Proposal).where(m.Proposal.call_id == call.id, m.Proposal.operation_id == operation_id))
    if not proposal:
        raise Rejected("not_found", "Operation not found", 404)
    booking = db.scalar(select(m.Booking).where(m.Booking.proposal_id == proposal.id))
    return {"operation_id": operation_id, "state": "COMMITTED" if booking else "NOT_STARTED",
            "booking": row(booking) if booking else None}


@app.post("/runtime/suppress")
def suppress(body: s.SuppressInput, call: CALL, db: DB):
    value = svc.suppress(db, call, body.utterance_event_id)
    return {"suppression_id": value.id, "effective": True}


@app.get("/runtime/safety")
def safety(call: CALL):
    return {"gas": GAS_ADVICE, "co": CO_ADVICE}


@app.post("/runtime/voicemail/claim")
def voicemail(call: CALL, db: DB):
    contact = db.scalar(select(m.CampaignContact).where(
        m.CampaignContact.customer_id == call.customer_id, m.CampaignContact.year == call.year).with_for_update())
    allowed = bool(contact and not contact.voicemail_claimed)
    if allowed:
        contact.voicemail_claimed = True
    return {"allowed": allowed}


@app.post("/runtime/finish")
def finish(body: s.FinishInput, call: CALL, db: DB):
    return row(svc.finalise(db, call, body.summary), {"session_token_hash"})


@app.get("/v1/quality", dependencies=OPERATOR)
def quality(db: DB):
    runs = db.scalars(select(m.QualityRun).order_by(m.QualityRun.created_at.desc())).all()
    return {"status": "NOT EVALUATED" if not runs else "runs_available", "runs": [row(r) for r in runs],
            "weights": {"voice": 35, "conversation": 35, "task": 15, "operations": 10, "cost": 5}}


@app.post("/internal/calls/{call_id}/recording", dependencies=RUNTIME)
async def save_recording(call_id: str, request: Request, db: DB):
    if not db.get(m.Call, call_id):
        raise Rejected("not_found", "Call not found", 404)
    if request.headers.get("content-type", "").split(";")[0] != "audio/ogg":
        raise Rejected("invalid_recording_type", "Use audio/ogg", 415)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_RECORDING_BYTES:
            raise Rejected("recording_too_large", "Recording exceeds the upload limit", 413)
        body.extend(chunk)
    call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
    key = hashlib.sha256(body).hexdigest() + ".ogg.enc"
    if call.recording_key and call.recording_key != key:
        raise Rejected("recording_collision", "A different recording is already attached", 409)
    key = store_recording(bytes(body))
    call.recording_key, call.media_state = key, "available"
    return {"call_id": call.id, "media_state": "available", "sha256": key[:64]}


@app.get("/v1/calls/{call_id}/recording", dependencies=OPERATOR)
def recording(call_id: str, db: DB):
    call = db.get(m.Call, call_id)
    if not call or not call.recording_key:
        raise Rejected("recording_unavailable", "Recording is not available", 404)
    return Response(read_recording(call.recording_key), media_type="audio/ogg", headers={
        "Content-Disposition": f'inline; filename="call-{call.id}.ogg"',
        "Cache-Control": "private, no-store",
    })


# Private managed candidate uses an isolated evaluation diary, never phone dispatch.
from brightwater.managed.gateway import install as install_managed  # noqa: E402

install_managed(app, operator, scoped_call)


from brightwater.office import install as install_office  # noqa: E402

install_office(app, operator)
