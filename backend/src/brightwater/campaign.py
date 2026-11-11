"""Automatic reminder selection and admission; never enables dialing itself."""
from datetime import timedelta

from sqlalchemy import func, select

from brightwater import models as m
from brightwater import services as svc
from brightwater.policy import UK, Rejected, now, uk_phone


def configuration_issues(cfg):
    issues = []
    if cfg.max_active_calls != 1:
        issues.append("The qualified gateway admits one call at a time")
    if not cfg.managed_enabled or not cfg.managed_api_key.get_secret_value() or len(cfg.managed_webhook_secret.get_secret_value()) < 32 or not getattr(cfg, 'managed_campaign_agent_id', ''):
        issues.append('Configure the separate ElevenLabs customer campaign agent')
    if not getattr(cfg, 'campaign_gateway_url', '').startswith('https://'):
        issues.append('Configure the verified UK campaign gateway; the India test route is separate')
    if len(getattr(cfg, 'campaign_gateway_token', cfg.voice_gateway_token).get_secret_value()) < 32:
        issues.append('Configure private campaign gateway authentication')
    if not cfg.campaign_route_verified and not cfg.campaign_pilot_customer_id:
        issues.append('Qualify the UK carrier route and approved caller ID before activation')
    try:
        uk_phone(cfg.office_callback_number)
    except Rejected:
        issues.append('Configure a real approved UK office callback number; assessment sample numbers are blocked')
    if not cfg.recording_notice:
        issues.append('Configure the customer recording notice')
    return issues


def due_customers(db, at=None):
    at = at or now()
    today = at.astimezone(UK).date()
    # One row per customer, including landlords with multiple due properties.
    # Overdue work goes to office review, not an endless historical autodial loop.
    return db.execute(select(m.Customer, func.min(m.Obligation.due_date).label('first_due'))
        .select_from(m.Customer).join(m.Property, m.Property.customer_id == m.Customer.id).join(m.Obligation, m.Obligation.property_id == m.Property.id).where(~m.Customer.id.startswith("ENGINEERING-"),
            m.Obligation.resolved.is_(False), m.Obligation.due_date >= today,
            m.Obligation.due_date <= today + timedelta(days=28))
        .group_by(m.Customer.id).order_by((m.Customer.kind != 'landlord'), func.min(m.Obligation.due_date), m.Customer.id)).all()


def enqueue_due(db, at=None):
    at = at or now()
    from brightwater.config import settings
    cfg = settings()
    if cfg.campaign_pilot_customer_id:
        return []  # Only an operator may start the attended pilot.
    queued = []
    start = at.astimezone(UK).replace(hour=0, minute=0, second=0, microsecond=0)
    dispatched = db.scalar(select(func.count()).select_from(m.Call).where(m.Call.purpose == 'campaign',
        m.Call.dispatched_at >= start, m.Call.dispatched_at < start + timedelta(days=1)))
    if dispatched >= cfg.campaign_daily_limit:
        return queued
    active = db.scalar(select(func.count()).select_from(m.Call).where(m.Call.state.in_(svc.ACTIVE)))
    budget = max(0, min(cfg.max_active_calls + 1 - active, cfg.campaign_daily_limit - dispatched))
    if not budget:
        return queued
    approved = set(db.scalars(select(m.Destination.customer_id).where(m.Destination.enabled.is_(True))))
    contacts = {c.customer_id: c for c in db.scalars(select(m.CampaignContact).where(
        m.CampaignContact.year == at.astimezone(UK).year))}
    for person, _ in due_customers(db, at):
        if person.id not in approved or person.contact_blocked:
            continue
        contact = contacts.get(person.id)
        if contact and (contact.stopped or contact.next_attempt_at and contact.next_attempt_at > at):
            continue
        # Request policy serialises destination, suppression, window and attempt
        # checks. Repeated Beat deliveries cannot create another active intent.
        try:
            with db.begin_nested():
                key = f'campaign:{person.id}:{at.astimezone(UK).date()}:{at.hour}'
                queued.append(svc.request_call(db, person.id, key, at=at).id)
                if len(queued) >= budget:
                    break
        except Rejected:
            continue
    return queued


def status(db, cfg):
    control = db.get(m.Control, 'dialing')
    issues = configuration_issues(cfg)
    if not cfg.dialing_enabled or not control or not control.enabled:
        issues.insert(0, 'Customer calling is paused')
    due = due_customers(db)
    return {'enabled': not issues, 'voice_backend': 'elevenlabs', 'lead_days': 28,
        'timezone': 'Europe/London', 'max_attempts': 3, 'minimum_retry_hours': 24,
        'due_customers': len(due), 'landlords_due': sum(c.kind == 'landlord' for c, _ in due),
        'blockers': issues, 'tenant_calls': False,
        'preview': [{'customer_id': c.id, 'customer_name': c.name, 'kind': c.kind,
            'due_date': day.isoformat()} for c, day in due[:20]]}


def voicemail_message_configured(call):
    from brightwater.config import settings
    return call.purpose == 'campaign' or (
        call.purpose == 'engineering' and bool(settings().engineering_callback_number.get_secret_value()))


def voicemail_result(db, call, evidence):
    """Claim a verified voicemail message once per customer and year."""
    from brightwater import schemas as s
    from brightwater.managed.boundaries import terminal_reason
    if terminal_reason(db, call, evidence) != 'voicemail':
        raise Rejected('evidence_pending', 'The existing voicemail detection is uncertain; do not disclose account details')
    contact = db.scalar(select(m.CampaignContact).where(m.CampaignContact.customer_id == call.customer_id,
        m.CampaignContact.year == call.year).with_for_update())
    if contact is None:
        if call.purpose != 'engineering':
            raise Rejected('campaign_missing', 'No campaign record exists for this voicemail')
        contact = m.CampaignContact(customer_id=call.customer_id, year=call.year)
        db.add(contact)
        db.flush()
    allowed = not contact.voicemail_claimed
    contact.voicemail_claimed = True
    from brightwater.config import settings
    cfg = settings()
    if call.purpose == 'engineering':
        import re
        number = cfg.engineering_callback_number.get_secret_value()
        allowed = allowed and bool(re.fullmatch(r'\+91[6-9]\d{9}', number))
        introduction = "This is Alex, Brightwater's automated assistant, leaving an engineering test message."
        callback = 'The approved test callback number is ' + ' '.join(number.lstrip('+')) + '.'
    else:
        introduction = "Hello, this is Brightwater Plumbing and Heating's automated assistant."
        try:
            number = uk_phone(cfg.office_callback_number)
        except Rejected:
            allowed = False
            number = ''
        callback = 'Please call our office on ' + ('0' + number[3:]) + '.'
    message = f'{introduction} {callback} Thank you.' if allowed else None
    if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id,
        m.CallEvent.provider_event_id == 'campaign-voicemail:' + call.id)):
        svc.record_event(db, call.id, s.EventInput(provider_event_id='campaign-voicemail:' + call.id,
            kind='voicemail', occurred_at=now(), payload={'source': 'verified_caller_automation',
                'source_event_id': evidence.source_id, 'message_authorised': allowed,
                'instruction': 'Authorisation is not proof the message was heard'}))
    return {'finished': True, 'message_allowed': allowed, 'approved_message': message,
        'close_with_native_end_call': True,
        'instruction': 'Speak only the approved_message if present, with no customer name, account, property or boiler details, then native end_call. Otherwise end politely without a voicemail message. Do not navigate menus or call another number.'}
