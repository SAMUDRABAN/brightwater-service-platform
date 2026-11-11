import hashlib
import json
from collections import Counter
from datetime import timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater.config import settings
from brightwater.policy import (
    OUTCOMES,
    SERVICES,
    UK,
    Rejected,
    allowed_time,
    explicit_opt_out,
    explicit_recording_refusal,
    explicit_yes,
    identity_affirmative,
    next_retry,
    now,
    self_identifies,
    time_band,
    uk_phone,
)

ACTIVE = ("queued", "dispatching", "unknown", "in_progress")


def control_lock(db: Session):
    # All calling-policy changes serialize; never hold this across a network request.
    db.execute(text("SELECT pg_advisory_xact_lock(72542190)"))


def customer(db, customer_id):
    value = db.get(m.Customer, customer_id)
    if not value:
        raise Rejected("not_found", "Customer not found", 404)
    return value


def verified(call):
    if not call.identity_verified or call.state != "in_progress":
        raise Rejected("identity_required", "Speak to the named customer before account access", 403)


def suppressed(db, customer_id, phone):
    return db.scalar(select(m.Suppression.id).where(
        or_(m.Suppression.customer_id == customer_id, m.Suppression.phone == phone)
    ).limit(1)) is not None


def register_destination(db, customer_id, phone, consent_reference):
    control_lock(db)
    customer(db, customer_id)
    uk_phone(phone)
    if suppressed(db, customer_id, phone):
        raise Rejected("suppressed", "This customer or destination is permanently suppressed")
    if db.scalar(select(m.Call.id).where(m.Call.customer_id == customer_id, m.Call.state.in_(ACTIVE))):
        raise Rejected("active_call", "Resolve the active call before changing its destination")
    dest = db.scalar(select(m.Destination).where(m.Destination.customer_id == customer_id))
    if not dest:
        dest = m.Destination(customer_id=customer_id, phone=phone, consent_reference=consent_reference)
        db.add(dest)
    dest.phone, dest.consent_reference, dest.enabled = phone, consent_reference, True
    dest.consented_at = now()
    db.flush()
    return dest


def check_dial_policy(db, c, dest, at, *, exclude_call=None):
    cfg = settings()
    if cfg.campaign_pilot_customer_id and (
        c.id != cfg.campaign_pilot_customer_id or not dest
        or dest.phone != cfg.campaign_pilot_recipient.get_secret_value()
    ):
        raise Rejected("pilot_recipient_mismatch", "Only the approved UK pilot customer and recipient may be called")
    if not allowed_time(at, c.not_before):
        raise Rejected("outside_calling_window", "Current UK time or the customer's preference blocks this call")
    if c.contact_blocked or not dest or not dest.enabled:
        raise Rejected("destination_not_approved", "An enabled, consented test destination is required")
    uk_phone(dest.phone)
    if suppressed(db, c.id, dest.phone):
        raise Rejected("suppressed", "This customer or number must not be called")
    year = at.astimezone(UK).year
    start = at.astimezone(UK).replace(hour=0, minute=0, second=0, microsecond=0)
    day_attempts = db.scalar(select(func.count()).select_from(m.Call).where(m.Call.purpose == "campaign",
        m.Call.dispatched_at >= start, m.Call.dispatched_at < start + timedelta(days=1),
        m.Call.id != exclude_call if exclude_call else True))
    if day_attempts >= settings().campaign_daily_limit:
        raise Rejected("daily_campaign_limit", "The bounded daily customer-call allowance has been used")
    contact = db.scalar(select(m.CampaignContact).where(
        m.CampaignContact.customer_id == c.id, m.CampaignContact.year == year))
    if contact and contact.stopped:
        raise Rejected("campaign_stopped", "A conversation or terminal outcome stopped this campaign")
    query = select(m.Call).join(m.Destination, m.Call.destination_id == m.Destination.id).where(
        or_(m.Call.customer_id == c.id, m.Destination.phone == dest.phone), m.Call.state.in_(ACTIVE))
    if exclude_call:
        query = query.where(m.Call.id != exclude_call)
    if db.scalar(query.limit(1)):
        raise Rejected("active_or_unknown_call", "Another call to this customer or destination is unresolved")
    attempts = db.scalars(select(m.Call).where(
        m.Call.customer_id == c.id, m.Call.year == year,
        m.Call.dispatched_at.is_not(None)).order_by(m.Call.dispatched_at.desc())).all()
    if exclude_call:
        attempts = [a for a in attempts if a.id != exclude_call]
    if len(attempts) >= 3:
        raise Rejected("attempts_exhausted", "Three attempts have already been dispatched")
    if attempts:
        last = attempts[0]
        if at - last.dispatched_at < timedelta(hours=24) or at.astimezone(UK).date() <= last.dispatched_at.astimezone(UK).date():
            raise Rejected("retry_too_soon", "Retries need 24 hours and a later UK date")
        if time_band(at) in {a.time_band for a in attempts}:
            raise Rejected("retry_band_used", "Use a different permitted time of day")


def request_call(db, customer_id, request_key, *, at=None):
    at = at or now()
    control_lock(db)
    existing = db.scalar(select(m.Call).where(m.Call.request_key == request_key))
    if existing:
        if existing.customer_id != customer_id:
            raise Rejected("idempotency_mismatch", "Request key already belongs to another customer")
        return existing
    c = customer(db, customer_id)
    dest = db.scalar(select(m.Destination).where(m.Destination.customer_id == customer_id))
    check_dial_policy(db, c, dest, at)
    year = at.astimezone(UK).year
    contact = db.scalar(select(m.CampaignContact).where(
        m.CampaignContact.customer_id == c.id, m.CampaignContact.year == year))
    if not contact:
        db.add(m.CampaignContact(customer_id=c.id, year=year))
    ordinal = db.scalar(select(func.count()).select_from(m.Call).where(
        m.Call.customer_id == c.id, m.Call.year == year, m.Call.dispatched_at.is_not(None))) + 1
    call = m.Call(customer_id=c.id, destination_id=dest.id, year=year, attempt=ordinal,
                  request_key=request_key, time_band=time_band(at), created_at=at,
                  release_id=settings().release_id)
    db.add(call)
    db.flush()
    db.add(m.Outbox(topic="calls.dispatch", aggregate_id=call.id))
    return call


def account(db, call):
    verified(call)
    c = customer(db, call.customer_id)
    properties = db.scalars(select(m.Property).where(m.Property.customer_id == c.id)).all()
    return {"customer_id": c.id, "name": c.name, "kind": c.kind,
            "reference_uk_date": now().astimezone(UK).date().isoformat(),
            "engineers": [{"id": e.id, "name": e.name, "gas_registered": e.gas_registered,
                           "bookable_services": list(SERVICES) if e.gas_registered else []}
                          for e in db.scalars(select(m.Engineer).where(m.Engineer.active.is_(True)).order_by(m.Engineer.name))],
            "properties": [
        {"id": p.id, "address": p.address, "boiler": p.boiler, "boiler_year": p.boiler_year,
         "replacement_quote_eligible": bool(p.boiler_year and now().astimezone(UK).year - p.boiler_year >= settings().replacement_quote_age_years),
         "obligations": [{"id": o.id, "service": o.service, "due_date": o.due_date.isoformat()} for o in db.scalars(
             select(m.Obligation).where(m.Obligation.property_id == p.id, m.Obligation.resolved.is_(False)))]}
        for p in properties]}


def availability(db, call, items, *, preferred_day=None, preferred_period=None, engineer_id=None, after_day=None, same_day=True):
    verified(call)
    if len({i.property_id for i in items}) != len(items):
        raise Rejected("duplicate_property", "Select one approved service per property", 422)
    deadlines = {}
    for item in items:
        prop = db.get(m.Property, item.property_id)
        if not prop or prop.customer_id != call.customer_id or item.service not in SERVICES:
            raise Rejected("invalid_service_property", "Invalid property or service", 422)
        services_due = ["service", "cp12"] if item.service == "combined" else [item.service]
        deadlines[item.property_id] = db.scalar(select(func.min(m.Obligation.due_date)).where(
            m.Obligation.property_id == prop.id, m.Obligation.service.in_(services_due),
            m.Obligation.resolved.is_(False)))
    if engineer_id is not None:
        engineer = db.get(m.Engineer, engineer_id)
        if not engineer or not engineer.active or not engineer.gas_registered:
            raise Rejected("engineer_unavailable", "That engineer cannot carry out these gas services. Choose an eligible active engineer from the account.", 422)
    query = select(m.DiaryWindow).join(m.Engineer).where(
        m.Engineer.gas_registered.is_(True), m.Engineer.active.is_(True),
        m.DiaryWindow.day >= now().astimezone(UK).date())
    for condition in [
        m.DiaryWindow.day == preferred_day if preferred_day else None,
        m.DiaryWindow.period == preferred_period if preferred_period else None,
        m.DiaryWindow.engineer_id == engineer_id if engineer_id else None,
        m.DiaryWindow.day > after_day if after_day else None,
    ]:
        if condition is not None:
            query = query.where(condition)
    windows = db.scalars(query.order_by(m.DiaryWindow.day, m.DiaryWindow.period, m.DiaryWindow.engineer_id)).all()
    engineers = {e.id: e for e in db.scalars(select(m.Engineer).where(m.Engineer.active.is_(True)))}
    existing_offers = list(db.scalars(select(m.AvailabilityOffer).where(
        m.AvailabilityOffer.call_id == call.id, m.AvailabilityOffer.expires_at > now()).order_by(
            m.AvailabilityOffer.expires_at.desc())))
    def selection(items):
        return [{k: i.get(k) for k in ("property_id", "service", "window_id", "day", "period", "engineer_id", "engineer_name", "engineer_requested")} for i in items]
    options = []
    def allocate(candidates):
        remaining = {w.id: w.capacity_minutes - w.used_minutes for w in candidates}
        proposed = []
        for item in sorted(items, key=lambda i: (-SERVICES[i.service]["minutes"], i.property_id)):
            duration = SERVICES[item.service]["minutes"]
            window = next((w for w in candidates if remaining[w.id] >= duration
                and (deadlines[item.property_id] is None or w.day <= deadlines[item.property_id])), None)
            if not window:
                return []
            remaining[window.id] -= duration
            proposed.append({"item_id": m.uid(), "property_id": item.property_id,
                "service": item.service, "window_id": window.id, "day": window.day.isoformat(),
                "period": window.period, "engineer_id": window.engineer_id,
                "engineer_name": engineers[window.engineer_id].name,
                "engineer_requested": engineer_id is not None})
        return proposed
    if not same_day:
        proposed = allocate(sorted(windows, key=lambda w: (w.day, w.period == "AFTERNOON", w.engineer_id)))
        if proposed:
            offer = next((o for o in existing_offers if selection(o.items) == selection(proposed)), None)
            if offer is None:
                offer = m.AvailabilityOffer(call_id=call.id, items=proposed, expires_at=now() + timedelta(minutes=5))
                db.add(offer)
                db.flush()
            return {"options": [{"offer_id": offer.id, "items": offer.items, "reserved": False}], "reserved": False, "reason": None}
    for day in sorted({w.day for w in windows}) if same_day else []:
        if any(deadline is not None and day > deadline for deadline in deadlines.values()):
            continue
        day_options = []
        for period in ("MORNING", "AFTERNOON"):
            proposed = allocate([w for w in windows if w.day == day and w.period == period])
            if proposed:
                day_options.append(proposed)
        if not day_options:
            # Same day need not mean the same arrival window for every landlord property.
            proposed = allocate(sorted([w for w in windows if w.day == day],
                key=lambda w: (w.period == "AFTERNOON", w.engineer_id)))
            if proposed:
                day_options.append(proposed)
        for proposed in day_options:
            offer = next((o for o in existing_offers if selection(o.items) == selection(proposed)), None)
            if offer is None:
                offer = m.AvailabilityOffer(call_id=call.id, items=proposed,
                                            expires_at=now() + timedelta(minutes=5))
                db.add(offer)
                db.flush()
            options.append({"offer_id": offer.id, "items": offer.items, "reserved": False})
            if len(options) == 2:
                break
        if len(options) == 2:
            break
    return {"options": options, "reserved": False,
            "preferences": {"day": preferred_day.isoformat() if preferred_day else None,
                            "period": preferred_period, "engineer_id": engineer_id,
                            "after_day": after_day.isoformat() if after_day else None},
            "reason": None if options else "No eligible space matches the requested dates, window and engineer before the due date"}


def prepare(db, call, offer_id, tenants):
    verified(call)
    offer = db.get(m.AvailabilityOffer, offer_id)
    if not offer or offer.call_id != call.id or offer.expires_at < now():
        raise Rejected("offer_expired", "Check the diary again")
    c = customer(db, call.customer_id)
    contacts = {t.property_id: t for t in tenants}
    cp12_count = sum(i["service"] == "cp12" for i in offer.items)
    items = []
    for item in offer.items:
        window = db.get(m.DiaryWindow, item["window_id"])
        if (not window or window.engineer_id != item["engineer_id"]
            or window.day.isoformat() != item["day"] or window.period != item["period"]):
            raise Rejected("offer_changed", "The offered date, window or engineer changed. Check the same requested preferences again")
        engineer = db.get(m.Engineer, window.engineer_id)
        if not engineer or not engineer.active or not engineer.gas_registered:
            raise Rejected("offer_changed", "That engineer is no longer eligible; review the requested preferences")
        prop = db.get(m.Property, item["property_id"])
        tenant = contacts.get(prop.id)
        if c.kind == "landlord" and not tenant:
            raise Rejected("tenant_required", "Tenant name and phone are required for each property", 422)
        spec = SERVICES[item["service"]]
        items.append({**item, "engineer_name": engineer.name,
                      "engineer_requested": item.get("engineer_requested", False),
                      "address": prop.address, "minutes": spec["minutes"],
                      "price_pence": 6000 if item["service"] == "cp12" and cp12_count >= 3 else spec["price_pence"],
                      "tenant_name": tenant.name if tenant else None, "tenant_phone": tenant.phone if tenant else None})
    digest = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    current = db.scalar(select(m.Proposal).where(m.Proposal.call_id == call.id,
        m.Proposal.fingerprint == digest, m.Proposal.state == "prepared", m.Proposal.expires_at > now()).order_by(m.Proposal.created_at.desc()))
    if current:
        return current
    proposal = m.Proposal(call_id=call.id, items=items, fingerprint=digest,
                          total_pence=sum(i["price_pence"] for i in items),
                          expires_at=now() + timedelta(seconds=settings().proposal_ttl_seconds))
    db.add(proposal)
    db.flush()
    return proposal


def commit(db, call_id, proposal_id, confirmation_event_id, *, consent=None):
    call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
    verified(call)
    proposal = db.scalar(select(m.Proposal).where(m.Proposal.id == proposal_id).with_for_update())
    if not proposal or proposal.call_id != call.id:
        raise Rejected("proposal_not_found", "Proposal not found", 404)
    existing = db.scalar(select(m.Booking).where(m.Booking.proposal_id == proposal.id))
    if existing:
        if existing.state != "confirmed":
            raise Rejected("booking_cancelled", "This arrangement was cancelled; prepare a fresh proposal")
        return existing
    if proposal.expires_at < now() or proposal.state != "prepared":
        raise Rejected("proposal_expired", "Prepare and confirm a new proposal")
    events = db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id).order_by(
        m.CallEvent.occurred_at, m.CallEvent.received_at)).all()
    confirmation = next((e for e in events if e.id == confirmation_event_id), None)
    readbacks = [e for e in events if e.kind == "readback_completed" and
                 e.payload.get("proposal_id") == proposal.id and
                 e.payload.get("fingerprint") == proposal.fingerprint]
    agreed = bool(confirmation and (consent.confirms(call.id, proposal, confirmation.payload.get("text", "")) if consent is not None else explicit_yes(confirmation.payload.get("text", ""))))
    if not confirmation or confirmation.kind != "user_utterance" or confirmation.payload.get("speech_timing_verified") is not True or not agreed or not readbacks:
        raise Rejected("confirmation_required", "A clear affirmative after a completed read-back is required")
    if next((e.id for e in reversed(events) if e.kind == "user_utterance"), None) != confirmation.id:
        raise Rejected("confirmation_superseded", "The customer spoke again; reconfirm the current proposal")
    readback = readbacks[-1]
    if next((e.id for e in reversed(events) if e.kind == "readback_completed"), None) != readback.id:
        raise Rejected("readback_superseded", "A newer proposal was read back; confirm that proposal instead")
    if confirmation.occurred_at <= readback.occurred_at or any(
        (e.kind in {"interruption", "speaker_changed", "gas_emergency", "co_alarm", "urgent"}
         or (e.kind == "user_utterance" and e.id != confirmation.id and (consent is not None or not explicit_yes(e.payload.get("text", "")))))
        and readback.occurred_at < e.occurred_at for e in events
    ):
        raise Rejected("readback_interrupted", "Repeat the corrected read-back and obtain fresh confirmation")
    if any(e.kind in {"gas_emergency", "co_alarm", "urgent"} or (e.kind == "semantic_turn" and e.payload.get("followup") in {"gas_emergency", "co_alarm", "urgent"}) for e in events):
        raise Rejected("unsafe_service_booking", "A reported urgent issue needs human follow-up")
    return reserve(db, call, proposal)


def reserve(db, call, proposal):
    """Reserve after a trusted adapter has validated its confirmation evidence.

    Call/proposal must be locked by the adapter in the same transaction.
    Phone runtime uses commit(); managed evaluations use their separate adapter.
    """
    # Serialise duplicate proposals from this call as well as shared diary capacity.
    call = db.scalar(select(m.Call).where(m.Call.id == call.id).with_for_update())
    if db.scalar(select(m.Booking.id).where(m.Booking.call_id == call.id,
        m.Booking.state == "confirmed", m.Booking.proposal_id != proposal.id).limit(1)):
        raise Rejected("booking_already_saved", "This call already saved an arrangement. Review it rather than creating another booking")
    dest = db.get(m.Destination, call.destination_id)
    if suppressed(db, call.customer_id, dest.phone):
        raise Rejected("suppressed", "Call was opted out; no new booking operation")
    hazards = db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
        m.CallEvent.kind == 'semantic_turn')).all()
    if any(e.payload.get('followup') in {'gas_emergency', 'co_alarm', 'urgent'} for e in hazards):
        raise Rejected('unsafe_service_booking', 'Urgent or emergency issues need human follow-up')
    ids = sorted({i["window_id"] for i in proposal.items})
    windows = {w.id: w for w in db.scalars(select(m.DiaryWindow).where(
        m.DiaryWindow.id.in_(ids)).order_by(m.DiaryWindow.id).with_for_update())}
    demand = Counter()
    for item in proposal.items:
        prop = db.get(m.Property, item["property_id"])
        window = windows.get(item["window_id"])
        engineer = db.get(m.Engineer, window.engineer_id) if window else None
        if not prop or prop.customer_id != call.customer_id or not engineer or not engineer.gas_registered or not engineer.active:
            raise Rejected("invalid_booking", "Property or engineer eligibility changed")
        if (window.engineer_id != item["engineer_id"] or window.day.isoformat() != item["day"]
            or window.period != item["period"]):
            raise Rejected("engineer_changed", "The offered date, window or engineer assignment changed. Review this selection and obtain fresh agreement before saving")
        demand[window.id] += SERVICES[item["service"]]["minutes"]
    if any(windows[k].used_minutes + minutes > windows[k].capacity_minutes for k, minutes in demand.items()):
        raise Rejected("capacity_conflict", "That space has just been booked; check the diary again")
    booking = m.Booking(proposal_id=proposal.id, call_id=call.id, customer_id=call.customer_id,
                        total_pence=proposal.total_pence)
    db.add(booking)
    db.flush()
    for item in proposal.items:
        db.add(m.BookingItem(booking_id=booking.id, property_id=item["property_id"],
                            window_id=item["window_id"], service=item["service"], duration_minutes=item["minutes"],
                            price_pence=item["price_pence"], tenant_name=item["tenant_name"], tenant_phone=item["tenant_phone"]))
        for obligation in db.scalars(select(m.Obligation).where(m.Obligation.property_id == item["property_id"])):
            if obligation.service == item["service"] or item["service"] == "combined":
                obligation.resolved = True
    for key, minutes in demand.items():
        windows[key].used_minutes += minutes
    proposal.state = "committed"
    stop_campaign(db, call)
    return booking


def stop_campaign(db, call):
    contact = db.scalar(select(m.CampaignContact).where(
        m.CampaignContact.customer_id == call.customer_id, m.CampaignContact.year == call.year))
    if contact:
        contact.stopped, contact.next_attempt_at = True, None


def suppress(db, call, utterance_event_id):
    control_lock(db)
    event = db.get(m.CallEvent, utterance_event_id)
    if not event or event.call_id != call.id or event.kind != "user_utterance":
        raise Rejected("evidence_required", "A caller utterance is required", 422)
    dest = db.get(m.Destination, call.destination_id)
    existing = db.scalar(select(m.Suppression).where(m.Suppression.phone == dest.phone,
        m.Suppression.customer_id == (call.customer_id if call.identity_verified else None)).limit(1))
    if not existing:
        existing = m.Suppression(phone=dest.phone, customer_id=call.customer_id if call.identity_verified else None,
                                 evidence=event.id)
        db.add(existing)
    dest.enabled = False
    stop_campaign(db, call)
    call.identity_verified = False
    for queued in db.scalars(select(m.Call).join(m.Destination).where(
        m.Destination.phone == dest.phone, m.Call.state == "queued")):
        queued.state, queued.outcome, queued.summary = "cancelled", "No answer", "Call cancelled before dispatch. This number was suppressed."
        queued.ended_at = now()
    db.flush()
    return existing


def answered_identity_question(db, call, source, expected):
    if not source or source.payload.get("speech_timing_verified") is not True or not identity_affirmative(source.payload.get("text", "")):
        return False
    events = db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id).order_by(m.CallEvent.occurred_at, m.CallEvent.received_at)).all()
    prompts = [e for e in events if e.kind == "turn_state" and e.payload.get("source") == "identity_question"]
    if not prompts:
        return False
    prompt = prompts[-1]
    question = "Am I speaking with " + expected + "?"
    if (prompt.payload.get("completed") is not True or prompt.payload.get("notice_delivered") is not True
        or prompt.payload.get("name") != expected or prompt.payload.get("text") != question
        or not prompt.occurred_at < source.occurred_at <= prompt.occurred_at + timedelta(seconds=60)
        or not timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
        return False
    # An old yes cannot answer a later question or survive a speaker handoff.
    return not any(prompt.occurred_at < e.occurred_at <= source.occurred_at and (
        e.kind in {"speaker_changed", "interruption"}
        or (e.kind == "agent_utterance" and (e.payload.get("text", "").strip() != question or e.payload.get("interrupted") is True))
    ) for e in events)


def record_event(db, call_id, event, *, identity_evidence=None):
    control_lock(db)
    call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
    if not call:
        raise Rejected("not_found", "Call not found", 404)
    existing = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
                                                 m.CallEvent.provider_event_id == event.provider_event_id))
    if existing:
        if existing.kind != event.kind or existing.payload != event.payload:
            raise Rejected("event_collision", "Event identity reused with different contents")
        return existing
    value = m.CallEvent(call_id=call.id, **event.model_dump())
    db.add(value)
    db.flush()
    if event.kind == "user_utterance" and explicit_opt_out(event.payload.get("text", "")):
        # Same transaction as the transcript: no model tool or identity check is
        # required to stop calling a number. Re-delivery returns the event above.
        suppress(db, call, value.id)
    if event.kind == "user_utterance" and explicit_recording_refusal(event.payload.get("text", "")):
        call.identity_verified = False
        stop_campaign(db, call)
        db.add(m.CallEvent(call_id=call.id, provider_event_id="recording-refused:" + value.id,
            kind="recording_refused", occurred_at=event.occurred_at,
            payload={"utterance_event_id": value.id, "source": "deterministic_transcript_guard"}))
        call.state, call.ended_at = "finished", now()
        call.summary = "The caller declined recording. The session was closed to further account access and business actions."
        db.flush()
    if event.kind == "connected" and call.state in {"dispatching", "unknown"}:
        call.state, call.media_state = "in_progress", "pending"
    elif event.kind == "identity_assertion" and call.state == "in_progress":
        source = db.get(m.CallEvent, event.payload.get("utterance_event_id", ""))
        expected = customer(db, call.customer_id).name
        latest = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
            m.CallEvent.kind.in_(["user_utterance", "speaker_changed"])).order_by(
                m.CallEvent.occurred_at.desc(), m.CallEvent.received_at.desc()).limit(1))
        spoken = source.payload.get("text", "") if source and source.call_id == call.id and source.kind == "user_utterance" else ""
        if identity_evidence is not None:
            from brightwater.managed.phone import identity_evidence_valid
            matched = bool(source and identity_evidence_valid(db, call, source, expected, identity_evidence))
        else:
            # Legacy adapter compatibility. The managed gateway always supplies
            # server-created semantic evidence, never this phrase path.
            matched = self_identifies(spoken, expected) or answered_identity_question(db, call, source, expected)
        if not source or not latest or latest.id != source.id or not isinstance(spoken, str) or not matched:
            raise Rejected("identity_uncertain", "Named customer identity is uncertain", 403)
        call.identity_verified, call.conversation = True, True
        stop_campaign(db, call)
    elif event.kind == "speaker_changed":
        call.identity_verified = False
    elif event.kind in {"gas_emergency", "co_alarm", "urgent", "complaint", "callback", "lead"}:
        kind = "gas" if event.kind in {"gas_emergency", "co_alarm"} else event.kind
        db.add(m.Followup(call_id=call.id, kind=kind, owner="Mark" if kind == "complaint" else "Sarah",
                         priority=0 if kind in {"gas", "urgent"} else 1 if kind == "complaint" else 2,
                         detail=str(event.payload.get("detail", "Reported during call"))[:1500],
                         requested=kind in {"callback", "lead"}))
    elif event.kind == "wrong_number":
        customer(db, call.customer_id).contact_blocked = True
        db.add(m.Followup(call_id=call.id, kind="wrong_number", owner="Sarah", priority=2,
                         detail="Verify and correct this customer's telephone number.", requested=False))
    if event.kind in {"no_answer", "busy", "failed", "ended"} or call.state == "finished":
        finalise(db, call, call.summary if call.state == "finished" and call.summary else
                 "Call ended without a completed arrangement. Review the recorded details where available.")
    return value


def finalise(db, call, summary):
    if call.state == "cancelled":
        return call
    events = db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)).all()
    kinds = {e.kind for e in events}
    answered = call.conversation or "connected" in kinds or any(
        e.payload.get("carrier_answered") is True and e.payload.get("source") in {
            "signed_plivo_status", "signed_twilio_status", "voice_gateway_failure", "voice_gateway_diagnostic_hold",
            "authenticated_carrier_reconciliation",
        } for e in events)
    facts = set()
    mapping = {"gas_emergency": "Gas emergency advice", "co_alarm": "Gas emergency advice",
               "urgent": "Urgent callback", "complaint": "Complaint", "callback": "Callback requested",
               "lead": "Lead", "not_interested": "Not interested", "serviced_elsewhere": "Serviced elsewhere",
               "wrong_number": "Wrong number", "not_available": "Not available", "voicemail": "Voicemail"}
    facts.update(mapping[k] for k in kinds if k in mapping)
    if db.scalar(select(m.Booking.id).where(m.Booking.call_id == call.id, m.Booking.state == "confirmed")):
        facts.add("Booked")
    if summary == "Call ended without a completed arrangement. Review the recorded details where available.":
        summary = ("A confirmed booking is saved in the diary. Review its visit details and the recording below."
                   if "Booked" in facts else "No confirmed booking remains for this call. Review its follow-ups and recording where available.")
    dest = db.get(m.Destination, call.destination_id)
    if suppressed(db, call.customer_id, dest.phone):
        facts.add("Do not call")
    technical_failure = answered and any(
        e.kind == "failed" and e.payload.get("source") in {"voice_gateway_failure", "signed_plivo_status", "signed_twilio_status"}
        for e in events
    )
    fallback = None
    if "recording_refused" not in kinds and call.purpose not in {"managed_evaluation", "browser_simulation"} and (not answered or technical_failure):
        fallback = "No answer"  # The assessment groups failed calls with No answer.

    call.outcome = next((o for o in OUTCOMES if o in facts), fallback)
    needs_review = call.outcome is None or (technical_failure and call.outcome == "No answer")
    if technical_failure and call.outcome == "No answer":
        summary = "The carrier answered, but a technical failure ended the call without a business outcome. Review before calling again."
    if needs_review and answered and "recording_refused" not in kinds and not any(e.kind == "turn_state" and e.payload.get("source") == "boundary_terminal_requested" for e in events) and not db.scalar(
        select(m.Followup.id).where(m.Followup.call_id == call.id, m.Followup.kind == "internal_review").limit(1)
    ):
        db.add(m.Followup(call_id=call.id, kind="internal_review", owner="Sarah", priority=1,
            detail="Answered call ended without a business outcome. Review the technical or identity issue before further contact.", requested=False))
    call.state, call.ended_at, call.summary = "finished", call.ended_at or now(), summary
    connected = db.scalar(select(func.min(m.CallEvent.occurred_at)).where(
        m.CallEvent.call_id == call.id, m.CallEvent.kind == "connected"))
    if call.purpose == "browser_simulation":
        connected = call.created_at
    call.duration_seconds = max(0, int((call.ended_at - connected).total_seconds())) if connected else 0
    if call.conversation or technical_failure or call.outcome not in {"No answer", "Voicemail", "Not available"}:
        stop_campaign(db, call)
    else:
        contact = db.scalar(select(m.CampaignContact).where(m.CampaignContact.customer_id == call.customer_id,
                                                           m.CampaignContact.year == call.year))
        attempts = db.scalars(select(m.Call).where(m.Call.customer_id == call.customer_id,
                                                 m.Call.year == call.year, m.Call.dispatched_at.is_not(None))).all()
        if contact:
            contact.next_attempt_at = next_retry(now(), {a.time_band for a in attempts}, customer(db, call.customer_id).not_before) if len(attempts) < 3 else None
    if call.media_state == "not_available" and not call.conversation:
        call.media_state = "not_applicable"
    return call
