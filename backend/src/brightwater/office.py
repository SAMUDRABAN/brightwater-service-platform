"""Staff CRM queries and audited follow-up work. Never dispatches telephone calls."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater import services as svc
from brightwater.db import get_db
from brightwater.office_bookings import BookingUpdate
from brightwater.policy import UK, Rejected, normalise_uk_phone, now

DB = Annotated[Session, Depends(get_db, scope="function")]


class FollowupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["resolve", "reopen", "assign"]
    owner: Literal["Sarah", "Mark"] | None = None
    note: str = Field(default="", max_length=1500)
    request_key: str = Field(pattern=r"^[a-f0-9-]{36}$")


class OutcomeReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    disposition: Literal["not_available", "wrong_number", "not_interested", "serviced_elsewhere", "voicemail"]
    note: str = Field(min_length=10, max_length=1500)


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_key: UUID
    name: str = Field(min_length=2, max_length=160)
    kind: Literal["homeowner", "landlord"]
    address: str = Field(min_length=6, max_length=300)
    notes: str = Field(default="", max_length=1500)
    service: Literal["service", "cp12", "combined"] | None = None
    due_date: date | None = None
    phone: str = Field(default="", max_length=32)
    consent_reference: str = Field(default="", max_length=300)


class ReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: str = Field(max_length=40)
    service: Literal["service", "cp12", "combined"]
    due_date: date


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schedule_at: datetime | None


def customer_audit(db, request, action, customer_id):
    actor = getattr(request.state, "staff", None)
    db.add(m.StaffAudit(username=actor.username if actor else "trusted_operator",
                        action=f"{action}: {customer_id}"))


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_before: time | None = None


CallScope = Literal["all", "campaign", "uk_test", "engineering", "browser_simulation"]


def call_type():
    return case((or_(m.Call.time_band == "uk_test", m.Call.customer_id.startswith("ENGINEERING-QUEUE-")), "uk_test"), else_=m.Call.purpose)


def displayed_purpose(call):
    return "uk_test" if call.time_band == "uk_test" or call.customer_id.startswith("ENGINEERING-QUEUE-") else call.purpose


def followup_row(db, value):
    call = db.get(m.Call, value.call_id)
    person = db.get(m.Customer, call.customer_id)
    return {
        "id": value.id,
        "call_id": call.id,
        "customer_id": person.id,
        "customer_name": person.name,
        "owner": value.owner,
        "kind": value.kind,
        "priority": value.priority,
        "detail": value.detail,
        "summary": call.summary,
        "media_state": call.media_state,
        "created_at": value.created_at,
        "purpose": displayed_purpose(call),
        "resolved": value.resolved,
    }


def call_row(call, name):
    return {
        "id": call.id,
        "customer_id": call.customer_id,
        "customer_name": name,
        "purpose": displayed_purpose(call),
        "state": call.state,
        "outcome": call.outcome,
        "outcome_review_required": call.outcome_review_required,
        "summary": call.summary,
        "created_at": call.created_at,
        "attempt": call.attempt,
        "duration_seconds": call.duration_seconds,
        "media_state": call.media_state,
    }


def install(app, operator):
    auth = [Depends(operator)]

    @app.get("/v1/office/followups", dependencies=auth)
    def followups(
        db: DB,
        status: Literal["open", "resolved", "all"] = "open",
        scope: CallScope = "all",
    ):
        query = select(m.Followup).join(m.Call, m.Call.id == m.Followup.call_id)
        if status != "all":
            query = query.where(m.Followup.resolved.is_(status == "resolved"))
        if scope != "all":
            query = query.where(call_type() == scope)
        return [
            followup_row(db, f)
            for f in db.scalars(query.order_by(m.Followup.priority, m.Followup.created_at))
        ]

    @app.post("/v1/office/followups/{followup_id}", dependencies=auth)
    def update_followup(followup_id: str, body: FollowupUpdate, request: Request, db: DB):
        value = db.scalar(select(m.Followup).where(m.Followup.id == followup_id).with_for_update())
        if not value:
            raise Rejected("not_found", "Follow-up not found", 404)
        actor = getattr(request.state, "staff", None)
        payload = {
            "source": "office_workflow",
            "followup_id": value.id,
            "action": body.action,
            "owner": body.owner,
            "note": body.note.strip(),
            "actor": actor.username if actor else "trusted_operator",
        }
        key = "office-followup:" + body.request_key
        prior = db.scalar(
            select(m.CallEvent).where(
                m.CallEvent.call_id == value.call_id, m.CallEvent.provider_event_id == key
            )
        )
        if prior:
            if prior.payload != payload:
                raise Rejected("request_collision", "This request key has already been used", 409)
            return followup_row(db, value)
        if body.action == "assign":
            if body.owner is None:
                raise Rejected("owner_required", "Choose Sarah or Mark", 422)
            if value.kind == "complaint" and body.owner != "Mark":
                raise Rejected("complaint_owner", "Complaints must remain assigned to Mark", 422)
            value.owner = body.owner
        else:
            value.resolved = body.action == "resolve"
        db.add(
            m.CallEvent(
                call_id=value.call_id,
                provider_event_id=key,
                kind="office_followup_updated",
                occurred_at=now(),
                payload=payload,
            )
        )
        db.flush()
        call = db.get(m.Call, value.call_id)
        if call.state in {"finished", "failed"}:
            from brightwater.call_results import refresh_result

            events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)))
            refresh_result(db, call, events, historical=True)
        return followup_row(db, value)

    @app.post("/v1/office/customers", dependencies=auth, status_code=201)
    def create_customer(body: CustomerInput, request: Request, db: DB):
        svc.control_lock(db)
        customer_id = "BW-C-" + body.request_key.hex
        if db.get(m.Customer, customer_id):
            return {"id": customer_id}
        if bool(body.service) != bool(body.due_date):
            raise Rejected("missing_reminder_details", "Choose a service and due date together", 422)
        if body.consent_reference and (not body.phone or len(body.consent_reference) < 10):
            raise Rejected("invalid_consent", "Supply a UK phone number and a consent reference of at least 10 characters", 422)
        phone = normalise_uk_phone(body.phone) if body.phone else ""
        db.add(m.Customer(id=customer_id, name=body.name, kind=body.kind, source_phone=phone, notes=body.notes))
        db.flush()
        property_id = m.uid()
        db.add(m.Property(id=property_id, customer_id=customer_id, address=body.address))
        db.flush()
        if body.service:
            db.add(m.Obligation(id=m.uid(), property_id=property_id, service=body.service, due_date=body.due_date))
        if body.consent_reference:
            svc.register_destination(db, customer_id, phone, body.consent_reference)
        customer_audit(db, request, "Created customer", customer_id)
        return {"id": customer_id}

    @app.post("/v1/office/customers/{customer_id}/reminders", dependencies=auth, status_code=201)
    def add_reminder(customer_id: str, body: ReminderInput, request: Request, db: DB):
        svc.control_lock(db)
        prop = db.get(m.Property, body.property_id)
        if not customer_id.startswith("BW-") or not prop or prop.customer_id != customer_id:
            raise Rejected("not_found", "Property not found on this customer record", 404)
        existing = db.scalar(select(m.Obligation).where(m.Obligation.property_id == prop.id,
            m.Obligation.service == body.service, m.Obligation.resolved.is_(False)).limit(1))
        if existing:
            if existing.due_date == body.due_date:
                return {"id": existing.id}
            raise Rejected("reminder_exists", "This property already has an outstanding reminder for that service")
        record = m.Obligation(id=m.uid(), property_id=prop.id, service=body.service, due_date=body.due_date)
        db.add(record)
        db.flush()
        customer_audit(db, request, "Added service reminder", customer_id)
        return {"id": record.id}

    @app.post("/v1/office/customers/{customer_id}/schedule", dependencies=auth)
    def schedule_call(customer_id: str, body: ScheduleInput, request: Request, db: DB):
        svc.control_lock(db)
        person = svc.customer(db, customer_id)
        if not customer_id.startswith("BW-"):
            raise Rejected("not_found", "Customer not found", 404)
        at = body.schedule_at
        if at is not None:
            if at.tzinfo is not None or at.second or at.microsecond:
                raise Rejected("invalid_schedule", "Use a UK date and time in hours and minutes", 422)
            at = at.replace(tzinfo=UK)
            current = now()
            if at <= current or at.date() > current.astimezone(UK).date() + timedelta(days=28):
                raise Rejected("invalid_schedule", "Choose a future UK date within the next 28 days", 422)
            if not db.scalar(select(m.Obligation.id).join(m.Property).where(
                m.Property.customer_id == person.id, m.Obligation.resolved.is_(False)).limit(1)):
                raise Rejected("no_reminder", "Add an outstanding service reminder before scheduling a call", 422)
            destination = db.scalar(select(m.Destination).where(m.Destination.customer_id == person.id))
            svc.check_dial_policy(db, person, destination, at, check_daily_limit=False)
        person.scheduled_call_at = at
        customer_audit(db, request, "Scheduled customer call" if at else "Removed scheduled call time", customer_id)
        return {"id": customer_id, "scheduled_call_at": at}

    @app.get("/v1/office/customers/{customer_id}", dependencies=auth)
    def customer(customer_id: str, db: DB):
        person = db.get(m.Customer, customer_id)
        if not person or not customer_id.startswith("BW-"):
            raise Rejected("not_found", "Customer not found", 404)
        properties = list(
            db.scalars(
                select(m.Property)
                .where(m.Property.customer_id == person.id)
                .order_by(m.Property.address)
            )
        )
        obligations = list(
            db.scalars(
                select(m.Obligation)
                .where(m.Obligation.property_id.in_([p.id for p in properties]))
                .order_by(m.Obligation.due_date)
            )
        )
        destination = db.scalar(select(m.Destination).where(m.Destination.customer_id == person.id))
        calls = list(
            db.scalars(
                select(m.Call)
                .where(m.Call.customer_id == person.id)
                .order_by(m.Call.created_at.desc())
                .limit(100)
            )
        )
        suppressed = bool(
            db.scalar(
                select(m.Suppression.id)
                .where(
                    or_(
                        m.Suppression.customer_id == person.id,
                        m.Suppression.phone
                        == (destination.phone if destination else person.source_phone),
                    )
                )
                .limit(1)
            )
        )
        return {
            "id": person.id,
            "name": person.name,
            "kind": person.kind,
            "notes": person.notes,
            "property_count": len(properties),
            "next_due": min((o.due_date for o in obligations if not o.resolved), default=None),
            "not_before": person.not_before,
            "contact_blocked": person.contact_blocked,
            "suppressed": suppressed,
            "destination_approved": bool(destination and destination.enabled),
            "destination_hint": ("Ending " + destination.phone[-4:]) if destination else None,
            "contact_phone": person.source_phone if person.id.startswith("BW-C-") else None,
            "scheduled_call_at": person.scheduled_call_at,
            "properties": [
                {
                    "id": p.id,
                    "address": p.address,
                    "boiler": p.boiler,
                    "boiler_year": p.boiler_year,
                    "obligations": [
                        {
                            "id": o.id,
                            "service": o.service,
                            "due_date": o.due_date,
                            "resolved": o.resolved,
                        }
                        for o in obligations
                        if o.property_id == p.id
                    ],
                }
                for p in properties
            ],
            "calls": [call_row(c, person.name) for c in calls],
        }

    @app.post("/v1/office/customers/{customer_id}/preferences", dependencies=auth)
    def preferences(customer_id: str, body: Preferences, request: Request, db: DB):
        svc.control_lock(db)
        person = db.scalar(select(m.Customer).where(m.Customer.id == customer_id).with_for_update())
        if not person or not customer_id.startswith("BW-"):
            raise Rejected("not_found", "Customer not found", 404)
        if body.not_before and (
            body.not_before.tzinfo is not None
            or body.not_before.second
            or body.not_before.microsecond
        ):
            raise Rejected("invalid_preference", "Use a UK local time in hours and minutes", 422)
        person.not_before = body.not_before
        actor = getattr(request.state, "staff", None)
        db.add(
            m.StaffAudit(
                username=actor.username if actor else "trusted_operator",
                action="Updated calling preference: " + customer_id,
            )
        )
        return {"id": person.id, "not_before": person.not_before}

    @app.get("/v1/office/calls", dependencies=auth)
    def calls(
        db: DB,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        scope: CallScope = "all",
        outcome: str = Query(default="", max_length=50),
    ):
        query = select(m.Call, m.Customer.name).join(
            m.Customer, m.Customer.id == m.Call.customer_id
        )
        if scope != "all":
            query = query.where(call_type() == scope)
        if q.strip():
            # Escape wildcard characters: the search box searches literal text.
            term = (
                "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
            query = query.where(
                or_(
                    m.Customer.name.ilike(term, escape="\\"),
                    m.Call.customer_id.ilike(term, escape="\\"),
                    m.Call.summary.ilike(term, escape="\\"),
                )
            )
        if outcome == "technical_review":
            query = query.where(m.Call.outcome_review_required.is_(True))
        elif outcome:
            query = query.where(
                m.Call.outcome.is_(None) if outcome == "unclassified" else m.Call.outcome == outcome
            )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(
            query.order_by(m.Call.created_at.desc(), m.Call.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [call_row(c, name) for c, name in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.post("/v1/office/calls/{call_id}/outcome", dependencies=auth)
    def review_outcome(call_id: str, body: OutcomeReview, request: Request, db: DB):
        from brightwater import schemas as s
        from brightwater import services as svc

        svc.control_lock(db)
        call = db.get(m.Call, call_id, with_for_update=True)
        if not call:
            raise Rejected("not_found", "Call not found", 404)
        key = "office-outcome-review"
        prior = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
                                                    m.CallEvent.provider_event_id == key))
        if prior:
            if prior.kind == body.disposition and prior.payload.get("note") == body.note:
                return {"outcome": call.outcome}
            raise Rejected("outcome_already_reviewed", "This attempt already has a staff outcome")
        if ((call.outcome is not None and not call.outcome_review_required)
            or call.state not in {"finished", "failed"} or call.purpose == "browser_simulation"):
            raise Rejected("outcome_review_unavailable", "Only a finished, unclassified telephone attempt can be reviewed")
        if db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.kind == "recording_refused").limit(1)):
            raise Rejected("outcome_review_unavailable", "The caller refused recording")
        staff = getattr(request.state, "staff", None)
        svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind=body.disposition,
            occurred_at=now(), payload={"source": "office_outcome_review", "note": body.note,
                                        "actor": staff.username if staff else "trusted_operator"}))
        if call.state == "failed":
            svc.finalise(db, call, call.summary)
        for item in db.scalars(select(m.Followup).where(m.Followup.call_id == call.id,
                                m.Followup.kind == "internal_review", m.Followup.resolved.is_(False))):
            item.resolved = True
        from brightwater.call_results import refresh_result
        refresh_result(db, call, list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id))), historical=True)
        return {"outcome": call.outcome}

    @app.get("/v1/office/diary", dependencies=auth)
    def diary(request: Request, db: DB):
        viewer = getattr(request.state, "staff", None)
        query = select(m.DiaryWindow, m.Engineer).join(
            m.Engineer, m.Engineer.id == m.DiaryWindow.engineer_id
        )
        if viewer and viewer.role == "engineer":
            query = query.where(m.Engineer.id == viewer.engineer_id)
        windows = list(
            db.execute(
                query.order_by(m.DiaryWindow.day, m.Engineer.name, m.DiaryWindow.period.desc())
            )
        )
        block_kind = case(
            (m.DiaryBlock.source == "assessment_prebooked_fixture", "pre_existing_work"),
            else_="blocked_time",
        )
        blocks = {}
        for window_id, kind, minutes in db.execute(
            select(m.DiaryBlock.window_id, block_kind, func.sum(m.DiaryBlock.minutes))
            .where(m.DiaryBlock.window_id.in_([w.id for w, _ in windows]))
            .group_by(m.DiaryBlock.window_id, block_kind).order_by(block_kind)
        ):
            blocks.setdefault(window_id, []).append({"kind": kind, "minutes": minutes})
        return [
            {
                "id": w.id,
                "day": w.day,
                "period": w.period,
                "engineer_id": e.id,
                "engineer": e.name,
                "gas_registered": e.gas_registered,
                "capacity_minutes": w.capacity_minutes,
                "used_minutes": w.used_minutes,
                "blocks": blocks.get(w.id, []),
            }
            for w, e in windows
        ]

    @app.post("/v1/office/bookings/{booking_id}", dependencies=auth)
    def update_booking(booking_id: str, body: BookingUpdate, request: Request, db: DB):
        from brightwater.office_bookings import update

        actor = getattr(request.state, "staff", None)
        return update(db, booking_id, body, actor.username if actor else "trusted_operator")

    @app.get("/v1/office/bookings/{booking_id}", dependencies=auth)
    def booking(booking_id: str, request: Request, db: DB):
        viewer = getattr(request.state, "staff", None)
        query = (
            select(m.Booking, m.BookingItem, m.DiaryWindow, m.Engineer, m.Property, m.Customer)
            .join(m.BookingItem, m.BookingItem.booking_id == m.Booking.id)
            .join(m.DiaryWindow, m.DiaryWindow.id == m.BookingItem.window_id)
            .join(m.Engineer, m.Engineer.id == m.DiaryWindow.engineer_id)
            .join(m.Property, m.Property.id == m.BookingItem.property_id)
            .join(m.Customer, m.Customer.id == m.Booking.customer_id)
            .where(m.Booking.id == booking_id)
        )
        if viewer and viewer.role == "engineer":
            query = query.where(m.Engineer.id == viewer.engineer_id)
        rows = list(db.execute(query.order_by(m.DiaryWindow.day, m.Property.address)))
        if not rows:
            raise Rejected("not_found", "Booking not found", 404)
        from brightwater.office_bookings import options, revision
        from brightwater.services import ACTIVE

        first = rows[0][0]
        call = db.get(m.Call, first.call_id)
        today = now().astimezone(UK).date()
        items = [row[1] for row in rows]
        editable = (not viewer or viewer.role != "engineer") and first.state == "confirmed" and call.state not in ACTIVE
        can_cancel = editable and all(row[2].day >= today for row in rows)
        available = options(db, [row[1] for row in rows if row[2].day >= today], today) if editable else {}
        viewer_is_engineer = viewer and viewer.role == "engineer"
        history = [] if viewer_is_engineer else [
            {"action": e.payload["action"], "note": e.payload["note"], "actor": e.payload["actor"], "at": e.occurred_at}
            for e in db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
                m.CallEvent.kind == "office_booking_updated").order_by(m.CallEvent.occurred_at.desc()))
            if e.payload.get("booking_id") == first.id
        ]
        return {
            "id": first.id,
            "state": first.state,
            "purpose": displayed_purpose(call),
            "revision": revision(db, first, items) if editable else None,
            "can_cancel": can_cancel,
            "history": history,
            "customer_name": rows[0][5].name,
            "customer_id": first.customer_id,
            "call_id": None if viewer and viewer.role == "engineer" else first.call_id,
            "items": [
                {
                    "id": item.id,
                    "rescheduling_options": available.get(item.id, []),
                    "address": prop.address,
                    "boiler": prop.boiler,
                    "service": item.service,
                    "day": window.day,
                    "period": window.period,
                    "engineer": engineer.name,
                    "price_pence": item.price_pence,
                    "duration_minutes": item.duration_minutes,
                    "tenant_name": item.tenant_name,
                    "tenant_phone": item.tenant_phone,
                }
                for _, item, window, engineer, prop, _ in rows
            ],
        }
