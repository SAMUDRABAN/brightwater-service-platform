"""Audited staff changes to existing diary reservations."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import services as svc
from brightwater.policy import UK, Rejected, now


class BookingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["reschedule", "cancel"]
    request_key: str = Field(pattern=r"^[a-f0-9-]{36}$")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    note: str = Field(min_length=1, max_length=1500)
    item_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")
    window_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")

    @model_validator(mode="after")
    def check_selection(self):
        if self.action == "reschedule" and (not self.item_id or not self.window_id):
            raise ValueError("Select a visit and a new diary window")
        if self.action == "cancel" and (self.item_id or self.window_id):
            raise ValueError("Cancel the booking as a whole")
        return self


def revision(db, booking, items):
    changes = db.scalar(select(func.count()).select_from(m.CallEvent).where(
        m.CallEvent.call_id == booking.call_id, m.CallEvent.kind == "office_booking_updated"))
    snapshot = [booking.state, sorted((item.id, item.window_id) for item in items), changes]
    return hashlib.sha256(json.dumps(snapshot).encode()).hexdigest()


def deadline(db, item):
    obligations = db.scalars(select(m.Obligation).where(m.Obligation.property_id == item.property_id))
    return min((due.due_date for due in obligations if svc.service_covers(item.service, due.service)), default=None)


def options(db, items, today):
    windows = list(db.execute(select(m.DiaryWindow, m.Engineer).join(m.Engineer)
        .where(m.DiaryWindow.day >= today, m.Engineer.active.is_(True), m.Engineer.gas_registered.is_(True))
        .order_by(m.DiaryWindow.day, m.DiaryWindow.period.desc(), m.Engineer.name)))
    result = {}
    for item in items:
        due = deadline(db, item)
        result[item.id] = [
            {"id": window.id, "day": window.day, "period": window.period, "engineer": engineer.name}
            for window, engineer in windows
            if window.id != item.window_id and (due is None or window.day <= due)
            and window.used_minutes + item.duration_minutes <= window.capacity_minutes
        ]
    return result


def update(db, booking_id, body, actor):
    reference = db.execute(select(m.Booking.call_id, m.Booking.proposal_id)
        .where(m.Booking.id == booking_id)).one_or_none()
    if reference is None:
        raise Rejected("not_found", "Booking not found", 404)
    call = db.get(m.Call, reference.call_id, with_for_update=True)
    proposal = db.get(m.Proposal, reference.proposal_id, with_for_update=True)
    booking = db.get(m.Booking, booking_id, with_for_update=True)
    items = list(db.scalars(select(m.BookingItem).where(m.BookingItem.booking_id == booking.id)))
    payload = {**body.model_dump(exclude={"request_key"}), "booking_id": booking.id,
               "source": "office_workflow", "actor": actor}
    key = "office-booking:" + body.request_key
    prior = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key))
    if prior:
        if any(prior.payload.get(k) != v for k, v in payload.items()):
            raise Rejected("request_collision", "This request key has already been used")
        return {"id": booking.id, "state": booking.state}
    if booking.state != "confirmed" or call.state in svc.ACTIVE:
        raise Rejected("booking_edit_unavailable", "Only a confirmed booking from a completed call can be changed")
    if body.revision != revision(db, booking, items):
        raise Rejected("booking_changed", "This booking changed while you were viewing it. Review it and try again")

    today = now().astimezone(UK).date()
    if body.action == "cancel":
        if any(db.get(m.DiaryWindow, item.window_id).day < today for item in items):
            raise Rejected("booking_in_past", "A booking with a past visit needs separate office review")
        payload["visits"] = [{"item_id": item.id, "window_id": item.window_id} for item in items]
        svc.release_booking(db, booking, items)
        proposal.state = "cancelled"
    else:
        item = next((item for item in items if item.id == body.item_id), None)
        if item is None or item.window_id == body.window_id:
            raise Rejected("invalid_visit", "Select a visit on this booking and a different diary window", 422)
        windows = svc.lock_diary_windows(db, {item.window_id, body.window_id})
        previous = windows.get(item.window_id)
        target = windows.get(body.window_id)
        engineer = db.get(m.Engineer, target.engineer_id) if target else None
        due = deadline(db, item)
        if not previous or previous.day < today:
            raise Rejected("booking_in_past", "A past visit cannot be moved")
        if not target or target.day < today or (due and target.day > due) or not engineer or not engineer.active or not engineer.gas_registered:
            raise Rejected("invalid_window", "Choose a current, eligible gas engineer window on or before the service due date", 422)
        svc.apply_diary_capacity(windows, {previous.id: -item.duration_minutes, target.id: item.duration_minutes})
        payload["previous_window_id"] = previous.id
        item.window_id = target.id
    db.add(m.CallEvent(call_id=call.id, provider_event_id=key,
        kind="office_booking_updated", occurred_at=now(), payload=payload))
    db.flush()
    from brightwater.call_results import refresh_result

    events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)))
    refresh_result(db, call, events, historical=True)
    return {"id": booking.id, "state": booking.state}
