"""Staff CRM queries and audited follow-up work. Never dispatches telephone calls."""

from datetime import time
from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater.db import get_db
from brightwater.policy import Rejected, now

DB = Annotated[Session, Depends(get_db, scope="function")]


class FollowupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["resolve", "reopen", "assign"]
    owner: Literal["Sarah", "Mark"] | None = None
    note: str = Field(default="", max_length=1500)
    request_key: str = Field(pattern=r"^[a-f0-9-]{36}$")


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_before: time | None = None


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
        "purpose": call.purpose,
        "resolved": value.resolved,
    }


def call_row(call, name):
    return {
        "id": call.id,
        "customer_id": call.customer_id,
        "customer_name": name,
        "purpose": call.purpose,
        "state": call.state,
        "outcome": call.outcome,
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
        scope: Literal["all", "campaign", "engineering"] = "all",
    ):
        query = select(m.Followup).join(m.Call, m.Call.id == m.Followup.call_id)
        if status != "all":
            query = query.where(m.Followup.resolved.is_(status == "resolved"))
        if scope != "all":
            query = query.where(m.Call.purpose == scope)
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
        return followup_row(db, value)

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
        scope: Literal["all", "campaign", "engineering"] = "all",
        outcome: str = Query(default="", max_length=50),
    ):
        query = select(m.Call, m.Customer.name).join(
            m.Customer, m.Customer.id == m.Call.customer_id
        )
        if scope != "all":
            query = query.where(m.Call.purpose == scope)
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
        if outcome:
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
            }
            for w, e in windows
        ]

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
        first = rows[0][0]
        return {
            "id": first.id,
            "state": first.state,
            "customer_name": rows[0][5].name,
            "customer_id": first.customer_id,
            "call_id": None if viewer and viewer.role == "engineer" else first.call_id,
            "items": [
                {
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
