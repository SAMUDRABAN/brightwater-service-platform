"""Cancel the current conversation's proposal/reservation, never a guessed appointment."""
from sqlalchemy import select

from brightwater import models as m
from brightwater import services as svc
from brightwater.policy import Rejected, now


def cancel(db, call, proposal_id, reply, consent, *, trusted_phone=False):
    call = db.get(m.Call, call.id, with_for_update=True)
    svc.verified(call)
    proposal = db.scalar(select(m.Proposal).where(m.Proposal.id == proposal_id, m.Proposal.call_id == call.id).with_for_update())
    if not proposal:
        raise Rejected('proposal_not_found', 'Identify the current arrangement first; do not guess another appointment')
    if consent is None or not consent.matches(call.id, proposal, reply) or consent.decision not in {'cancel', 'decline'}:
        raise Rejected('cancellation_unclear', 'Ask which arrangement they want to cancel; nothing has been cancelled')
    source = None
    if trusted_phone:
        from brightwater.managed.phone import caller_evidence
        source = caller_evidence(db, call, reply)
    booking = db.scalar(select(m.Booking).where(m.Booking.proposal_id == proposal.id).with_for_update())
    if booking and booking.state == 'confirmed':
        if consent.decision != 'cancel':
            raise Rejected('cancellation_unclear', 'The saved appointment needs an explicit cancellation request; do not infer one from a refusal of something else')
        items = db.scalars(select(m.BookingItem).where(m.BookingItem.booking_id == booking.id)).all()
        svc.release_booking(db, booking, items)
    proposal.state = 'cancelled'
    key = 'managed-cancel:' + proposal.id
    if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
        db.add(m.CallEvent(call_id=call.id, provider_event_id=key, kind='booking_cancelled', occurred_at=now(), payload={
            'proposal_id': proposal.id, 'booking_id': booking.id if booking else None,
            'source': 'managed_semantic_intent', 'caller_event_id': source.id if source else None,
            'reply': reply, 'decision': consent.decision}))
    db.flush()
    return {'cancelled': True, 'booking_was_saved': booking is not None,
            'instruction': 'The current arrangement is cancelled. Acknowledge once. Do not book again or invent a callback.'}
