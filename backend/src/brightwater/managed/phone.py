"""Trusted carrier evidence adapter. Never infers original speech from a model."""
import re
import time
from datetime import timedelta

from sqlalchemy import select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.managed.understanding import semantic_readback
from brightwater.policy import Rejected, now


def same_utterance(left, right):
    def normalise(text):
        return " ".join(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())
    return normalise(left) == normalise(right)


def caller_evidence(db, call, text):
    source = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
        m.CallEvent.kind.in_(["user_utterance", "speaker_changed"])).order_by(
            m.CallEvent.occurred_at.desc(), m.CallEvent.received_at.desc()).limit(1))
    if (not source or source.kind != "user_utterance"
        or source.payload.get("source") != "plivo_elevenlabs_observer"
        or source.payload.get("speech_timing_verified") is not True
        or not same_utterance(source.payload.get("text", ""), text)
        or not timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
        raise Rejected("evidence_pending", "The existing reply is being checked against the carrier evidence; do not ask the customer to repeat it yet")
    return source


def completed_question_valid(db, call, source, evidence):
    """Contextual assent needs an actual, current, completed question."""
    playback = db.get(m.CallEvent, evidence.playback_id)
    if (not playback or playback.call_id != call.id or playback.kind != 'agent_utterance'
        or playback.payload.get('source') != 'plivo_elevenlabs_observer'
        or playback.payload.get('playback_completed') is not True or playback.payload.get('interrupted') is not False
        or not playback.occurred_at < source.occurred_at <= playback.occurred_at + timedelta(seconds=60)
        or not same_utterance(playback.payload.get('text', ''), evidence.question)):
        return False
    events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
        m.CallEvent.occurred_at < source.occurred_at).order_by(m.CallEvent.occurred_at, m.CallEvent.received_at)))
    preceding = [e for e in events if e.kind in {'agent_utterance', 'interruption', 'speaker_changed'}]
    pending = [e for e in events if e.kind == 'turn_state' and e.payload.get('source') == 'managed_agent_prompt']
    return bool(preceding and preceding[-1].id == playback.id and (not pending or
        (pending[-1].payload.get('native_event_id'), pending[-1].payload.get('revision')) ==
        (playback.payload.get('native_event_id'), playback.payload.get('revision'))))


def notice_delivered(db, call, source, evidence, *, allow_after_source=False):
    events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)))
    handoff = max((e.occurred_at for e in events if e.kind == 'speaker_changed'), default=None)
    # A caller may volunteer their own name before the greeting finishes.
    # Disclosure must finish before account access, not before that volunteered
    # name. Early contextual yes still cannot answer an unheard name question.
    cutoff = now() if allow_after_source else source.occurred_at
    notice = any(e.kind == "turn_state" and e.payload.get("notice_delivered") is True
        and e.payload.get("completed") is True and e.occurred_at < cutoff
        and (handoff is None or e.occurred_at > handoff) for e in events)
    playback = db.get(m.CallEvent, evidence.playback_id)
    valid_playback = bool(playback and playback.call_id == call.id and playback.kind == "agent_utterance"
        and playback.payload.get("source") == "plivo_elevenlabs_observer"
        and playback.payload.get("playback_completed") is True and playback.payload.get("interrupted") is False
        and playback.occurred_at < source.occurred_at)
    meaning = evidence.meaning
    # A naturally worded notice can be verified from actual completed speech,
    # never from the caller, a queued caption or a model-supplied action flag.
    if valid_playback and meaning and meaning.notice_complete and meaning.notice_quote.strip():
        text = ' '.join(playback.payload.get('text', '').split()).casefold()
        notice = notice or (' '.join(meaning.notice_quote.split()).casefold() in text
                           and (handoff is None or playback.occurred_at > handoff))
    return notice


def identity_evidence_valid(db, call, source, expected, evidence):
    if (source is None or source.call_id != call.id or source.kind != "user_utterance"
        or source.payload.get("source") != "plivo_elevenlabs_observer"
        or source.payload.get("speech_timing_verified") is not True
        or not timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)
        or evidence is None or not evidence.matches(call.id, expected, source.payload.get("text", ""))
        or evidence.source_id != source.id or evidence.meaning.identity not in {"self", "assent"}):
        return False
    events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id).order_by(
        m.CallEvent.occurred_at, m.CallEvent.received_at)))
    handoff = max((e.occurred_at for e in events if e.kind == "speaker_changed"), default=None)
    playback = db.get(m.CallEvent, evidence.playback_id)
    valid_playback = bool(playback and playback.call_id == call.id and playback.kind == "agent_utterance"
        and playback.payload.get("source") == "plivo_elevenlabs_observer"
        and playback.payload.get("playback_completed") is True and playback.payload.get("interrupted") is False
        and playback.occurred_at < source.occurred_at)
    notice = notice_delivered(db, call, source, evidence, allow_after_source=evidence.named_self())
    if not notice:
        return False
    if evidence.named_self():
        return not (handoff and handoff >= source.occurred_at)
    if not valid_playback or not evidence.identity_question_grounded() or source.occurred_at > playback.occurred_at + timedelta(seconds=60):
        return False
    preceding = [e for e in events if e.kind in {"agent_utterance", "interruption", "speaker_changed"}
                 and e.occurred_at < source.occurred_at]
    if not preceding or preceding[-1].id != playback.id:
        return False
    if ' '.join(playback.payload.get('text', '').split()).casefold() != ' '.join(evidence.question.split()).casefold():
        return False
    pending = [e for e in events if e.kind == "turn_state" and e.payload.get("source") == "managed_agent_prompt"
               and e.occurred_at < source.occurred_at]
    if pending and (pending[-1].payload.get("native_event_id"), pending[-1].payload.get("revision")) != (
        playback.payload.get("native_event_id"), playback.payload.get("revision")):
        return False
    return not any(playback.occurred_at < e.occurred_at <= source.occurred_at
        and e.kind in {"interruption", "speaker_changed"} for e in events)


def identity(db, call, text, *, understanding=None):
    source = caller_evidence(db, call, text)
    expected = svc.customer(db, call.customer_id).name
    if not identity_evidence_valid(db, call, source, expected, understanding):
        if understanding is not None and not notice_delivered(db, call, source, understanding, allow_after_source=True):
            return {"verified": False, "reason": "notice_incomplete",
                "instruction": ("The current speaker has not heard the notice. Explain you are Brightwater Plumbing and Heating’s automated assistant and the call is recorded, then naturally check the intended customer. Do not disclose account details." if call.purpose == "campaign" else "The current speaker has not heard the complete notice. Briefly explain you are Brightwater's AI assistant on a recorded engineering test with fictional details, then naturally check you are speaking with the intended customer. Do not disclose account details or blame their wording.")}
        return {"verified": False, "instruction": "The disclosure has already completed. Do not repeat the disclosure or full opening. Ask once whether the named customer is speaking, then use confirm_identity on their fresh reply, including a volunteered name. Do not disclose account details or invent a callback."}
    svc.record_event(db, call.id, s.EventInput(provider_event_id="managed-identity:" + source.id,
        kind="identity_assertion", occurred_at=now(), payload={"utterance_event_id": source.id}),
        identity_evidence=understanding)
    account = svc.account(db, call)
    from brightwater.managed.readback import spoken_address
    for prop in account["properties"]:
        prop["address"] = spoken_address({"property_id": prop["id"], "address": prop["address"]})
    from brightwater.managed.account import identity_result
    return identity_result(account)


def commit(db, call, proposal_id, text, *, consent=None, understanding=None):
    source = caller_evidence(db, call, text)
    proposal = db.get(m.Proposal, proposal_id)
    if not proposal or proposal.call_id != call.id:
        raise Rejected("proposal_not_found", "Prepare this caller's proposal first")
    playback = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
        m.CallEvent.kind.in_(["agent_utterance", "interruption", "speaker_changed"])).order_by(
            m.CallEvent.occurred_at.desc(), m.CallEvent.received_at.desc()).limit(1))
    if (not playback or playback.kind != "agent_utterance" or playback.payload.get("source") != "plivo_elevenlabs_observer"
        or playback.payload.get("playback_completed") is not True or playback.payload.get("interrupted") is not False
        or playback.occurred_at <= proposal.created_at
        or not semantic_readback(understanding, proposal, playback.payload.get("text", ""))):
        raise Rejected("readback_incomplete", "Read all the prepared details, including the postcode, and wait for a fresh reply after playback finishes")
    svc.record_event(db, call.id, s.EventInput(provider_event_id="managed-readback:" + playback.id + ":" + proposal.id,
        kind="readback_completed", occurred_at=playback.occurred_at,
        payload={"proposal_id": proposal.id, "fingerprint": proposal.fingerprint,
                 "source": "verified_carrier_playout", "playback_event_id": playback.id}))
    if consent is not None and consent.question and not same_utterance(consent.question, playback.payload.get("text", "")):
        raise Rejected("confirmation_superseded", "The reply must answer the current completed readback")
    booking = svc.commit(db, call.id, proposal.id, source.id, consent=consent)
    return {"confirmed": True, "booking_id": booking.id, "total_pence": booking.total_pence,
            "purpose": call.purpose, "evidence_contract": "carrier_playout_and_original_speech",
            "close_with_native_end_call": True,
            "instruction": "The booking is saved. Briefly confirm it and payment to the engineer, then use native end_call. Do not call finish_conversation first: the authenticated carrier end event finalises this phone record."}


def wait_for_caller(db_factory, call_id, text, timeout=1.5):
    """Gateway transcript and provider tool may arrive in either network order.

    No SQL/control lock is held while waiting. Each read is a fresh,
    short transaction. An early reply retains its original timestamp throughout.
    """
    until = time.monotonic() + timeout
    while True:
        with db_factory() as db:
            call = db.get(m.Call, call_id)
            if not call or call.purpose not in {"engineering", "campaign"} or call.state != "in_progress":
                return False
            try:
                caller_evidence(db, call, text)
                return True
            except Rejected:
                pass
        if time.monotonic() >= until:
            return False
        time.sleep(.04)
