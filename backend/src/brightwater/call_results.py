"""Build call records from saved business facts and authenticated call evidence."""
from sqlalchemy import select

from brightwater import models as m
from brightwater.policy import OUTCOMES

NON_PHONE = {"browser_simulation", "managed_evaluation"}
OUTCOME_EVENTS = {
    "gas_emergency": "Gas emergency advice", "co_alarm": "Gas emergency advice",
    "urgent": "Urgent callback", "complaint": "Complaint", "callback": "Callback requested",
    "lead": "Lead", "not_interested": "Not interested", "serviced_elsewhere": "Serviced elsewhere",
    "wrong_number": "Wrong number", "not_available": "Not available", "voicemail": "Voicemail",
}
REQUESTS = {
    "Booked": "The customer agreed to the service arrangements",
    "Callback requested": "The caller asked for office help",
    "Urgent callback": "The caller reported an urgent problem",
    "Gas emergency advice": "The caller reported a gas smell or a carbon monoxide alarm",
    "Complaint": "The caller raised a complaint",
    "Lead": "The caller asked about work outside the standard service booking",
    "Not interested": "The caller declined the service",
    "Serviced elsewhere": "The caller reported the work had already been done elsewhere",
    "Do not call": "The caller asked Brightwater to stop calling",
    "Wrong number": "The person answering said the named customer was not at this number",
    "Not available": "Someone answered and said the named customer was unavailable",
    "Voicemail": "The call reached an answerphone",
}
TASK_ACTIONS = {
    "callback": "Sarah should call back during office hours",
    "urgent": "Sarah should prioritise the urgent callback",
    "gas": "Sarah should prioritise reviewing the recorded emergency details",
    "complaint": "Mark should review and handle the complaint",
    "lead": "Sarah should follow up on the quote enquiry",
    "wrong_number": "Sarah should check and correct the contact record",
    "internal_review": "Sarah should review the available call evidence before any further contact",
}


def call_evidence(call, events):
    answered = call.conversation or any(
        e.kind in {"connected", "recording_refused"} or (
            e.payload.get("carrier_answered") is True and e.payload.get("source") in {
                "signed_plivo_status", "signed_twilio_status", "voice_gateway_failure",
                "voice_gateway_diagnostic_hold", "authenticated_carrier_reconciliation",
            }
        ) for e in events
    )
    return answered


def refresh_result(db, call, events, *, historical=False):
    """Maintain disposition and staff-review status without scheduling work."""
    kinds = {e.kind for e in events}
    answered = call_evidence(call, events)
    facts = {OUTCOME_EVENTS[k] for k in kinds if k in OUTCOME_EVENTS}
    bookings = list(db.scalars(select(m.Booking).where(m.Booking.call_id == call.id)))
    booked = [booking for booking in bookings if booking.state == "confirmed"]
    if booked or (historical and bookings and call.outcome == "Booked"):
        facts.add("Booked")
    utterance_ids = [e.id for e in events if e.kind == "user_utterance"]
    if utterance_ids and db.scalar(select(m.Suppression.id).where(m.Suppression.evidence.in_(utterance_ids)).limit(1)):
        facts.add("Do not call")
    if historical and call.outcome in OUTCOMES and call.outcome != "No answer":
        facts.add(call.outcome)
    outcome = next((value for value in OUTCOMES if value in facts), None)
    if not outcome and call.purpose in NON_PHONE:
        # An unfinished browser/lab conversation is not a failed phone attempt.
        return answered, False
    historical_gap = historical and call.outcome is None
    technical_review = bool(not outcome and (answered or historical_gap or call.outcome_review_required)
                            and "recording_refused" not in kinds)
    call.outcome = outcome or "No answer"
    call.outcome_review_required = technical_review
    tasks = list(db.scalars(select(m.Followup).where(m.Followup.call_id == call.id)
        .order_by(m.Followup.resolved, m.Followup.priority, m.Followup.created_at, m.Followup.id)))
    active = next((task for task in tasks if not task.resolved and task.kind in TASK_ACTIONS
                   and task.kind != "internal_review"), None)
    if active:
        action = TASK_ACTIONS[active.kind].replace("Sarah should", f"{active.owner} should")
    elif technical_review:
        action = TASK_ACTIONS["internal_review"]
    elif "recording_refused" in kinds or call.outcome == "Do not call":
        action = "Leave automated calling stopped for this record"
    elif call.outcome in {"No answer", "Voicemail", "Not available"}:
        action = "Any further attempt is subject to the calling and retry rules"
    else:
        action = "No office follow-up is open for this call"

    if "recording_refused" in kinds:
        request = "The caller declined recording"
        saved = "Alex ended account access and stopped automated retries"
    else:
        request = REQUESTS.get(call.outcome, "The line connected without a confirmed business outcome" if answered
                               else "The attempt ended without evidence of a live answer")
        if booked:
            visits = list(db.execute(select(m.BookingItem, m.DiaryWindow, m.Engineer)
                .join(m.DiaryWindow, m.DiaryWindow.id == m.BookingItem.window_id)
                .join(m.Engineer, m.Engineer.id == m.DiaryWindow.engineer_id)
                .where(m.BookingItem.booking_id.in_([booking.id for booking in booked]))
                .order_by(m.DiaryWindow.day, m.DiaryWindow.period.desc(), m.Engineer.name)))
            if len(visits) == 1:
                _, window, engineer = visits[0]
                saved = f"Alex saved a {window.period.lower()} visit on {window.day:%d %B} with {engineer.name}"
            else:
                saved = f"Alex saved {len(visits)} visits in the diary"
        elif bookings:
            saved = "The original booking is now cancelled in the diary"
        elif call.outcome == "Do not call":
            saved = "The opt-out was saved"
        elif call.outcome == "Voicemail":
            saved = "Alex recorded the voicemail outcome"
        elif active and active.kind != "internal_review":
            saved = f"Alex saved a follow-up for {active.owner}"
        elif tasks and any(t.resolved and t.kind != "internal_review" for t in tasks):
            saved = "The saved office follow-up has been completed"
        else:
            saved = "No booking was saved"
    call.summary = f"{request}. {saved}. {action}."
    return answered, technical_review
