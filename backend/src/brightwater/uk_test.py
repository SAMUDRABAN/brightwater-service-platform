"""One operator-initiated UK assessment call, separate from the campaign queue."""

import hashlib
import re
import secrets
from datetime import date, timedelta

from sqlalchemy import func, select

from brightwater import models as m
from brightwater import services as svc
from brightwater.policy import UK, Rejected, now, uk_phone
from brightwater.seed import CUSTOMERS

UK_TEST_BAND = "uk_test"
UK_TEST_PREFIX = "ENGINEERING-UK-"
UK_TEST_SECONDS = 600


def is_uk_test(call):
    return bool(call and call.time_band == UK_TEST_BAND and call.customer_id.startswith(UK_TEST_PREFIX))


def available(db, cfg):
    control = db.get(m.Control, UK_TEST_BAND)
    return (cfg.uk_test_enabled and cfg.environment in {"production", "staging"}
            and bool(cfg.campaign_gateway_url and cfg.campaign_gateway_token.get_secret_value())
            and cfg.managed_enabled and cfg.managed_phone_enabled
            and bool(cfg.uk_test_caller_id.get_secret_value())
            and bool(cfg.managed_campaign_agent_id and cfg.media_encryption_key.get_secret_value())
            and (control is None or control.enabled))


def normalise_phone(value):
    cleaned = re.sub(r"[\s().-]", "", value)
    if cleaned.startswith("0044"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("0"):
        cleaned = "+44" + cleaned[1:]
    return uk_phone(cleaned)


def prepare(db, cfg, body):
    svc.control_lock(db)
    if not available(db, cfg):
        raise Rejected("uk_test_disabled", "The UK test route is paused or unavailable")
    number = normalise_phone(body.phone.get_secret_value())
    if number == cfg.uk_test_caller_id.get_secret_value():
        raise Rejected("invalid_destination", "Enter the recipient’s number rather than Alex’s caller ID", 422)
    if not body.consent:
        raise Rejected("consent_required", "Confirm the recipient agreed to a recorded test", 422)
    fixture = next((item for item in CUSTOMERS if item[0] == body.customer_id), None)
    if not fixture:
        raise Rejected("not_found", "Select a fictional assessment customer", 404)
    template_id, name, kind, _, preference, _, properties = fixture
    key = "uk-test:" + body.request_key
    previous = db.scalar(select(m.Call).where(m.Call.request_key == key))
    if previous:
        destination = db.get(m.Destination, previous.destination_id)
        if not is_uk_test(previous) or destination.phone != number or not previous.customer_id.startswith(UK_TEST_PREFIX + template_id + "-"):
            raise Rejected("request_conflict", "The request already belongs to a different test")
        return previous, None
    at = now()
    if svc.suppressed(db, template_id, number):
        raise Rejected("suppressed", "The recipient opted out")
    if db.scalar(select(m.Call.id).where(m.Call.state.in_(svc.ACTIVE)).limit(1)):
        raise Rejected("call_in_progress", "Resolve the current call before another test")
    start = at.astimezone(UK).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(select(func.count()).select_from(m.Call).where(m.Call.time_band == UK_TEST_BAND,
        m.Call.dispatched_at >= start, m.Call.dispatched_at < start + timedelta(days=1)))
    if used >= cfg.uk_test_daily_limit:
        raise Rejected("uk_test_limit", "Today’s UK test allowance has been used")

    customer = m.Customer(id=UK_TEST_PREFIX + template_id + "-" + m.uid()[:10], name=name,
        kind=kind, source_phone="UK assessment roleplay", not_before=preference,
        notes="Attended UK roleplay with fictional details.")
    db.add(customer)
    db.flush()
    for address, boiler, year, service, due in properties:
        prop = m.Property(id=m.uid(), customer_id=customer.id, address=address,
                          boiler=boiler, boiler_year=year)
        db.add(prop)
        db.flush()
        db.add(m.Obligation(id=m.uid(), property_id=prop.id, service=service, due_date=date.fromisoformat(due)))
    destination = m.Destination(customer_id=customer.id, phone=number, enabled=True,
                                consent_reference="Operator confirmed consent to one recorded UK roleplay.")
    db.add(destination)
    db.flush()
    db.add(m.CampaignContact(customer_id=customer.id, year=at.astimezone(UK).year))
    token = secrets.token_urlsafe(40)
    call = m.Call(customer_id=customer.id, destination_id=destination.id, year=at.astimezone(UK).year,
        attempt=1, request_key=key, purpose="campaign", state="dispatching", time_band=UK_TEST_BAND,
        dispatched_at=at, release_id=cfg.release_id, session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        summary="Attended UK roleplay with consent and fictional account details.")
    db.add(call)
    db.flush()
    return call, token
