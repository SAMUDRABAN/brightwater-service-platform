"""Explicit attended engineering calls; never a relaxation of UK campaign policy."""
import hashlib
import secrets

from sqlalchemy import func, select

from brightwater import models as m
from brightwater import services as svc
from brightwater.policy import Rejected, now, time_band


def prepare_engineering(db, cfg, request_key, *, scenario="standard"):
    customer_id = "ENGINEERING-LANDLORD" if scenario == "landlord" else "ENGINEERING-SAMUDRA"
    if not cfg.engineering_enabled or cfg.environment not in {"production", "staging", "local"}:
        raise Rejected("engineering_disabled", "Attended engineering calling is not enabled")
    phone = cfg.engineering_recipient.get_secret_value()
    if not phone.startswith("+91") or not cfg.engineering_consent_reference:
        raise Rejected("engineering_not_configured", "A privately allowlisted consented recipient is required")
    svc.control_lock(db)
    control = db.get(m.Control, "engineering")
    if control and not control.enabled:
        raise Rejected("engineering_paused", "Attended engineering calls have been paused")
    previous = db.scalar(select(m.Call).where(m.Call.request_key == request_key))
    if previous:
        if previous.purpose != "engineering" or previous.customer_id != customer_id:
            raise Rejected("request_conflict", "Request key belongs to a different operation")
        return previous, None
    if db.scalar(select(func.count()).select_from(m.Call).where(m.Call.state.in_(svc.ACTIVE))):
        raise Rejected("call_in_progress", "Resolve the current call before another attended test")
    attempts = db.scalar(select(func.count()).select_from(m.Call).where(m.Call.purpose == "engineering"))
    if attempts >= cfg.engineering_call_limit:
        raise Rejected("engineering_limit", "The bounded attended-call allowance is exhausted")
    if svc.suppressed(db, customer_id, phone):
        raise Rejected("suppressed", "The engineering recipient opted out")
    person = db.get(m.Customer, customer_id)
    if not person:
        landlord = scenario == "landlord"
        template_id = "BW-1056" if landlord else "BW-1041"
        properties = list(db.scalars(select(m.Property).where(
            m.Property.customer_id == template_id).order_by(m.Property.id)))
        if not properties:
            raise Rejected("assessment_required", "Seed labelled assessment fixtures before the engineering test")
        person = m.Customer(id=customer_id, name="Graham Okafor" if landlord else cfg.engineering_display_name,
            kind="landlord" if landlord else "homeowner", source_phone="Private engineering recipient",
            notes="ATTENDED ENGINEERING ROLEPLAY. Property and diary are fictional assessment fixtures; never campaign.")
        db.add(person)
        db.flush()
        for index, source in enumerate(properties, start=1):
            property_id = f"{customer_id}-P{index}" if landlord else "ENGINEERING-P1"
            db.add(m.Property(id=property_id, customer_id=person.id, address="Fictional engineering property — " + source.address,
                boiler=source.boiler, boiler_year=source.boiler_year))
            db.flush()
            obligations = list(db.scalars(select(m.Obligation).where(m.Obligation.property_id == source.id)))
            for position, due in enumerate(obligations, start=1):
                obligation_id = f"{property_id}-O{position}" if landlord else "ENGINEERING-SERVICE"
                db.add(m.Obligation(id=obligation_id, property_id=property_id, service=due.service, due_date=due.due_date))
    destination = db.scalar(select(m.Destination).where(m.Destination.customer_id == person.id))
    if not destination:
        destination = m.Destination(customer_id=person.id, phone=phone,
            consent_reference=cfg.engineering_consent_reference, enabled=True)
        db.add(destination)
        db.flush()
    if destination.phone != phone or not destination.enabled:
        raise Rejected("engineering_destination_changed", "Review the existing engineering destination explicitly")
    token = secrets.token_urlsafe(40)
    call = m.Call(customer_id=person.id, destination_id=destination.id, year=now().year,
        attempt=attempts + 1, request_key=request_key, purpose="engineering", state="dispatching",
        time_band=time_band(now()), dispatched_at=now(), release_id=cfg.release_id,
        session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        summary="Attended engineering roleplay with an explicitly consented recipient; not a customer campaign.")
    db.add(call)
    db.flush()
    return call, token
