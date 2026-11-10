"""Contextual purpose limits. No caller phrase lists, contact bans or diary writes."""
from datetime import timedelta

from sqlalchemy import select

from brightwater import models as m
from brightwater.policy import now

CONDUCT = frozenset({'off_topic', 'harassment'})
AUTOMATED = frozenset({'automated_menu', 'voicemail'})
BOUNDARIES = CONDUCT | AUTOMATED
CLOSING = "I'll end this call now. Thank you for your time. Goodbye."


def business_request(meaning):
    # Conflicting classifications favour hearing the enquiry. A conduct label
    # must not override an identified callback, quote, complaint or arrangement.
    return meaning.followup != 'none' or (
        meaning.appointment in {'confirm', 'decline', 'change', 'cancel'}
        and meaning.appointment_target != 'none')


def terminal_reason(db, call, evidence):
    """Only fresh observer turns and actually played warnings permit termination.

    Unknown/unclassified intervening turns break the streak. Model retries and
    different snapshots of one utterance never count as additional misconduct.
    """
    meaning = evidence.meaning
    if not meaning or meaning.control not in BOUNDARIES:
        return None
    person = db.get(m.Customer, call.customer_id)
    if not person or not evidence.matches(call.id, person.name, evidence.reply):
        return None
    if business_request(meaning):
        return None
    source = db.get(m.CallEvent, evidence.source_id)
    if (call.purpose not in {'engineering', 'campaign'} or not source or source.call_id != call.id
        or source.kind != 'user_utterance'
        or source.payload.get('source') != 'plivo_elevenlabs_observer'
        or source.payload.get('text', '').strip() != evidence.reply.strip()
        or source.payload.get('speech_timing_verified') is not True
        or not timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
        return None
    rows = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)
                           .order_by(m.CallEvent.occurred_at, m.CallEvent.received_at)))
    users = [e for e in rows if e.kind == 'user_utterance'
             and e.payload.get('source') == 'plivo_elevenlabs_observer']
    if not users or users[-1].id != source.id:
        return None
    if meaning.control in AUTOMATED:
        return meaning.control
    # Two harassment turns or three unrelated turns, with a real warning
    # between earlier misconduct and the latest turn. No warning means no end.
    count = 2 if meaning.control == 'harassment' else 3
    recent = users[-count:]
    if len(recent) < count:
        return None
    decisions = {}
    warnings = []
    for row in rows:
        if row.kind == 'semantic_turn':
            key = row.payload.get('source_event_id')
            decisions.setdefault(key, set()).add(row.payload.get('control'))
            if row.payload.get('boundary_warning_grounded') is True:
                speech = db.get(m.CallEvent, row.payload.get('playback_event_id'))
                if (speech and speech.call_id == call.id and speech.kind == 'agent_utterance'
                    and speech.payload.get('source') == 'plivo_elevenlabs_observer'
                    and speech.payload.get('playback_completed') is True
                    and speech.payload.get('interrupted') is False):
                    warnings.append(speech)
    if any(not decisions.get(e.id) or not decisions[e.id] <= CONDUCT for e in recent):
        return None
    if not any(recent[0].occurred_at < w.occurred_at < source.occurred_at for w in warnings):
        return None
    return meaning.control


def stopped_message(reason):
    return {'stopped': True, 'boundary_reason': reason,
            'instruction': 'This call is ending with a brief polite goodbye. Do not continue, disclose account details, retry tools, create a callback or change any saved arrangement.'}
