"""Authoritative call arrangement facts shared by voice tools and the office."""
from sqlalchemy import select

from brightwater import models as m
from brightwater.managed.readback import readback_text, spoken_address
from brightwater.policy import now


def current(db, call):
    booking = db.scalar(select(m.Booking).where(m.Booking.call_id == call.id,
        m.Booking.state == "confirmed").order_by(m.Booking.created_at.desc()))
    proposal = db.get(m.Proposal, booking.proposal_id) if booking else db.scalar(
        select(m.Proposal).where(m.Proposal.call_id == call.id).order_by(m.Proposal.created_at.desc()))
    if not booking and proposal:
        booking = db.scalar(select(m.Booking).where(m.Booking.proposal_id == proposal.id))
    if proposal is None:
        return {"status": "none", "saved": False, "reserved": False, "items": [],
                "instruction": "No arrangement has been prepared or saved in this call."}
    items = []
    if booking:
        rows = db.execute(select(m.BookingItem, m.DiaryWindow, m.Engineer, m.Property)
            .join(m.DiaryWindow, m.DiaryWindow.id == m.BookingItem.window_id)
            .join(m.Engineer, m.Engineer.id == m.DiaryWindow.engineer_id)
            .join(m.Property, m.Property.id == m.BookingItem.property_id)
            .where(m.BookingItem.booking_id == booking.id).order_by(m.DiaryWindow.day, m.Property.address))
        for item, window, engineer, prop in rows:
            items.append({"property_id": prop.id, "address": spoken_address({"property_id": prop.id, "address": prop.address}),
                "service": item.service, "day": window.day.isoformat(), "period": window.period,
                "engineer_id": engineer.id, "engineer_name": engineer.name,
                "gas_registered": engineer.gas_registered, "price_pence": item.price_pence})
        status = booking.state
    else:
        for item in proposal.items:
            window = db.get(m.DiaryWindow, item["window_id"])
            engineer = db.get(m.Engineer, item["engineer_id"])
            items.append({"property_id": item["property_id"], "address": spoken_address(item),
                "service": item["service"], "day": item["day"], "period": item["period"],
                "engineer_id": item["engineer_id"], "engineer_name": engineer.name if engineer else None,
                "gas_registered": bool(engineer and engineer.gas_registered), "price_pence": item["price_pence"],
                "assignment_changed": not window or window.engineer_id != item["engineer_id"] or window.day.isoformat() != item["day"] or window.period != item["period"] or not engineer or not engineer.active or not engineer.gas_registered})
        status = ("not_booked" if call.state in {"finished", "failed", "cancelled"}
                  else "expired" if proposal.expires_at <= now() else proposal.state)
    confirmed = bool(booking and booking.state == "confirmed")
    return {"status": status, "saved": confirmed, "reserved": confirmed,
        "booking_id": booking.id if booking else None, "proposal_id": proposal.id,
        "expires_at": proposal.expires_at.isoformat(), "total_pence": booking.total_pence if booking else proposal.total_pence,
        "items": items, "readback": readback_text(proposal),
        "instruction": ("This booking is already saved and the listed engineers are assigned in the diary. Do not create a duplicate."
            if confirmed else "This is a proposal, not a saved or held booking. Keep the selected details while answering questions. Only search different dates when requested, expired or unavailable; obtain authorisation after the actual full details have been heard.")}
