"""Business adapter for provider events in an isolated, labelled evaluation DB.

No SDK speech-timing proof is fabricated. These are managed evaluation turns,
not evidence accepted by the existing telephone runtime.
"""
import re
from datetime import timedelta
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.call_limits import ATTENDED_SESSION_TTL_SECONDS
from brightwater.config import settings
from brightwater.managed.readback import readback_text
from brightwater.managed.understanding import semantic_readback
from brightwater.policy import (
    Rejected,
    explicit_opt_out,
    explicit_recording_refusal,
    now,
)


@lru_cache
def lab_engine():
    cfg = settings()
    url = cfg.managed_database_url.get_secret_value()
    if not url or make_url(url).database != "brightwater_managed_evaluation" or make_url(url).database == make_url(cfg.database_url.get_secret_value()).database:
        raise Rejected("managed_isolation", "Managed evaluation requires its own dedicated database", 503)
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)


def create_evaluation(db, customer_id):
    customer = db.get(m.Customer, customer_id)
    if not customer or customer_id.startswith("ENGINEERING-"):
        raise Rejected("not_found", "Choose an assessment fixture", 404)
    if db.scalar(select(m.Call.id).where(m.Call.state == "in_progress")):
        raise Rejected("managed_busy", "Finish the active evaluation first")
    dest = db.scalar(select(m.Destination).where(m.Destination.customer_id == customer_id))
    if not dest:
        # Non-dialable label, not a routable number. No outbox, workers or dispatch.
        dest = m.Destination(customer_id=customer_id, phone="MANAGED-EVALUATION", enabled=False,
                             consent_reference="Non-phone managed evaluation; fictional fixtures only")
        db.add(dest)
        db.flush()
    call = m.Call(customer_id=customer_id, destination_id=dest.id, year=now().year, attempt=1,
                  purpose="managed_evaluation", request_key=m.uid(), state="in_progress", time_band="evaluation",
                  release_id=settings().release_id)
    db.add(call)
    db.flush()
    return {"id": call.id, "customer_name": customer.name, "purpose": call.purpose}


def create_diary_simulation(db, customer_id):
    from datetime import date

    from brightwater.seed import CUSTOMERS
    fixture = next((row for row in CUSTOMERS if row[0] == customer_id), None)
    if not fixture:
        raise Rejected("not_found", "Choose a fictional assessment fixture", 404)
    _, name, kind, _, _, _, properties = fixture
    customer = m.Customer(id="ENGINEERING-BROWSER-" + m.uid()[:16],
        name=name + " (browser test)", kind=kind, source_phone="Browser roleplay",
        contact_blocked=True, notes="Fictional browser simulation; excluded from telephone campaigns.")
    db.add(customer)
    db.flush()
    for address, boiler, year, service, due in properties:
        prop = m.Property(id=m.uid(), customer_id=customer.id, address=address, boiler=boiler, boiler_year=year)
        db.add(prop)
        db.flush()
        db.add(m.Obligation(id=m.uid(), property_id=prop.id, service=service, due_date=date.fromisoformat(due)))
    dest = m.Destination(customer_id=customer.id, phone="BROWSER-" + m.uid()[:20], enabled=False,
        consent_reference="Browser roleplay only; no telephone destination")
    db.add(dest)
    db.flush()
    call = m.Call(customer_id=customer.id, destination_id=dest.id, year=now().year, attempt=1,
        purpose="browser_simulation", request_key=m.uid(), state="in_progress", time_band="evaluation",
        release_id=settings().release_id)
    db.add(call)
    db.flush()
    return {"id": call.id, "customer_name": customer.name, "purpose": call.purpose}


class Conversation:
    def __init__(self, call_id, *, text_only=False, trusted_phone=False):
        self.call_id, self.text_only = call_id, text_only
        self.trusted_phone = trusted_phone
        self.turns = []
        self.results = {}
        self.readbacks = {}
        self.closed = False
        self.intent = None
        self.understanding = None
        self.callback_previously_declined = False

    def user(self, text):
        if isinstance(text, str) and text.strip():
            self.turns.append({"role": "user", "text": text[:4000], "interrupted": False})

    def agent(self, text):
        self.turns.append({"role": "agent", "text": text[:8000], "interrupted": False})

    def interrupt(self):
        for turn in reversed(self.turns):
            if turn["role"] == "agent":
                turn["interrupted"] = True
                break

    def latest_user(self):
        return next((t for t in reversed(self.turns) if t["role"] == "user"), None)

    def previous_agent(self):
        user = self.latest_user()
        before = self.turns[:self.turns.index(user)] if user else self.turns
        return next((t for t in reversed(before) if t["role"] == "agent"), None)

    def event(self, db, call, kind, payload, key=None):
        value = m.CallEvent(call_id=call.id, provider_event_id=key or m.uid(), kind=kind,
                            occurred_at=now(), payload={"source": "elevenlabs_managed_phone" if self.trusted_phone else "elevenlabs_managed_evaluation", **payload})
        db.add(value)
        db.flush()
        return value

    def execute(self, db, name, args, tool_id):
        if tool_id in self.results:
            return self.results[tool_id]
        if self.trusted_phone:
            svc.control_lock(db)
        call = db.scalar(select(m.Call).where(m.Call.id == self.call_id).with_for_update())
        max_age = ATTENDED_SESSION_TTL_SECONDS if self.trusted_phone else 240
        if not call or call.purpose not in ({"engineering", "campaign"} if self.trusted_phone else {"managed_evaluation", "browser_simulation"}) or call.state != "in_progress" or call.created_at < now() - timedelta(seconds=max_age):
            raise Rejected("managed_closed", "Evaluation session is absent, expired or closed", 403)
        utterance = self.latest_user()
        text = utterance["text"] if utterance else ""
        if self.understanding is not None:
            from brightwater.managed.semantic_runtime import apply_control, record_meaning
            if not self.understanding.matches(call.id, svc.customer(db, call.customer_id).name, text):
                raise Rejected("interpretation_unavailable", "I cannot reliably check this request right now. No change was saved; do not request another special phrase or repeated yes.")
            if self.trusted_phone:
                from brightwater.managed.semantic_runtime import snapshot
                from brightwater.managed.understanding import snapshot_digest
                current = snapshot(db, call, conversation=self, proposal_id=self.understanding.proposal_id or None)
                if snapshot_digest(current) != self.understanding.digest:
                    raise Rejected("evidence_pending", "The conversation changed while this request was checked. Recheck the current reply without asking for special wording.")
            record_meaning(db, call, self.understanding)
            if apply_control(db, call, self.understanding):
                self.closed = True
                from brightwater.managed.boundaries import BOUNDARIES, stopped_message
                if self.understanding.meaning.control in BOUNDARIES:
                    return stopped_message(self.understanding.meaning.control)
                return {"stopped": True, "opt_out": self.understanding.meaning.control == "stop_calling", "instruction": "The caller's stop/privacy request was saved. Close politely without account disclosure or further persuasion."}
        if (self.understanding and self.understanding.meaning.disposition != "none"
            and name not in {"finish_conversation", "record_followup"}):
            raise Rejected("intent_decline", "Respect the current decision. Do not offer dates or ask for another yes; close politely after recording the outcome.")
        # Independent safety fast paths remain; they are not the exclusive
        # vocabulary accepted by the managed semantic path.
        if explicit_opt_out(text) or explicit_recording_refusal(text):
            call.identity_verified = False
            call.state, call.ended_at = "finished", now()
            self.closed = True
            result = {"stopped": True, "opt_out": explicit_opt_out(text) and not explicit_recording_refusal(text), "instruction": "Respect the stop request. Close politely; do not disclose account information."}
        elif name == "confirm_identity" and self.trusted_phone:
            from brightwater.managed.phone import identity
            result = identity(db, call, text, understanding=self.understanding)
        elif name == "confirm_identity":
            customer = db.get(m.Customer, call.customer_id)
            previous = self.previous_agent()
            evidence = self.understanding
            if evidence is None or not evidence.matches(call.id, customer.name, text):
                raise Rejected("interpretation_unavailable", "Identity could not be checked. Do not blame the caller's wording or disclose the account.")
            meaning = evidence.meaning
            identified = evidence.named_self() or bool(meaning.identity in {"self", "assent"} and evidence.identity_question_grounded()
                and previous and not previous["interrupted"] and ' '.join(previous["text"].split()).casefold() == ' '.join(evidence.question.split()).casefold())
            call.identity_verified = identified
            if identified:
                call.conversation = True
                self.event(db, call, "identity_assertion", {"evidence": text, "contract": "managed_ordered_turns"})
                from brightwater.managed.account import identity_result
                result = identity_result(svc.account(db, call))
            else:
                result = {"verified": False, "instruction": "Clarify who is speaking once in natural language. Preserve the booking goal; do not invent a callback or claim identity confirmed."}
        elif name == "review_arrangement":
            svc.verified(call)
            from brightwater.arrangements import current
            result = current(db, call)
        elif name == "check_availability":
            body = s.AvailabilityInput.model_validate(args)
            result = svc.availability(db, call, body.items, preferred_day=body.preferred_day,
                preferred_period=body.preferred_period, engineer_id=body.engineer_id, after_day=body.after_day, same_day=body.same_day)
            # Actual engineer identity is a business fact; internal capacity counters stay private.
            result = {**result, "options": [{"offer_id": o["offer_id"], "reserved": False,
                "items": [{k: v for k, v in i.items() if k in {"property_id", "service", "day", "period", "engineer_id", "engineer_name", "engineer_requested"}} for i in o["items"]]} for o in result["options"]],
                "instruction": "These are available offers, not saved or held bookings. Explain the actual returned engineer if asked. Preserve the caller's choice while answering questions; review_arrangement shows the current selection."}
        elif name == "prepare_booking":
            # Contacts are required only for landlord access. A native model may
            # send placeholders even though the homeowner has no tenants.
            svc.verified(call)
            homeowner = svc.customer(db, call.customer_id).kind == "homeowner"
            body = s.PrepareInput.model_validate({**args, "tenants": []} if homeowner else args)
            from brightwater.arrangements import current
            existing = current(db, call)
            if existing["saved"]:
                return {**existing, "confirmed": True, "instruction": "The arrangement is already saved. Review the existing booking; do not create a duplicate."}
            proposal = svc.prepare(db, call, body.offer_id, body.tenants)
            readback = readback_text(proposal)
            self.readbacks[proposal.id] = {"text": readback, "turn_index": len(self.turns)}
            postcodes = [match.group(0) for item in proposal.items
                         if (match := re.search(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", item["address"]))]
            account = svc.account(db, call)
            eligible = any(p["replacement_quote_eligible"] for p in account["properties"] if p["id"] in {i["property_id"] for i in proposal.items})
            offered = db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id,
                m.CallEvent.kind.in_(["replacement_quote_offered", "lead"])).limit(1))
            quote_offer = bool(eligible and not offered)
            if quote_offer:
                self.event(db, call, "replacement_quote_offered", {"source": "verified_account_age", "proposal_id": proposal.id})
            result = {"proposal_id": proposal.id, "readback": readback, "confirmed": False,
                      "optional_quote_offer": quote_offer,
                      "arrangement": current(db, call), "required_postcodes": postcodes,
                      "instruction": ("Before the full booking readback, offer ONE optional replacement-quote enquiry and WAIT if the caller has not declined extras or asked to proceed directly. Record actual interest as lead, no replacement price. Then give the full current booking readback and await fresh booking authorisation. " if quote_offer else "") + "Explain every returned fact including the full address and postcode, date, window, total price, VAT and payment. Natural wording is welcome. Ask whether to save it and wait for the reply; no special consent phrase is required."}
        elif name == "confirm_booking":
            if self.intent is not None:
                self.event(db, call, "booking_intent", {"decision": self.intent.decision,
                    "proposal_id": self.intent.proposal_id, "fingerprint": self.intent.fingerprint,
                    "model": settings().managed_interpretation_model, "contract": "server_semantic_latest_reply"})
            result = self.confirm(db, call, args.get("proposal_id", ""))
            if result.get("confirmed"):
                from brightwater.arrangements import current
                result["arrangement"] = current(db, call)
        elif name == "cancel_arrangement":
            from brightwater.managed.cancellation import cancel
            result = cancel(db, call, args.get("proposal_id", ""), text, self.intent, trusted_phone=self.trusted_phone)
        elif name == "record_followup":
            kind = args.get("kind")
            if kind not in {"callback", "complaint", "urgent", "gas_emergency", "co_alarm", "lead"}:
                raise Rejected("invalid_followup", "Unsupported follow-up", 422)
            if not text:
                raise Rejected("evidence_required", "No caller evidence")
            if self.trusted_phone:
                from brightwater.managed.phone import caller_evidence
                source = caller_evidence(db, call, text)
                if self.understanding and self.understanding.meaning and self.understanding.meaning.followup_basis == "contextual":
                    from brightwater.managed.phone import completed_question_valid
                    if not completed_question_valid(db, call, source, self.understanding):
                        raise Rejected("evidence_pending", "The reply must answer the actual completed offer; do not invent a callback.")
            if not self.followup_requested(text, kind):
                result = {"saved": False, "instruction": "No explicit request found. This is not a system error. Do not claim a request was recorded. Preserve the caller's booking goal."}
            else:
                detail = self.followup_detail(db, call, text, kind)
                existing = db.scalar(select(m.Followup).where(m.Followup.call_id == call.id,
                    m.Followup.kind == kind, m.Followup.detail == detail).limit(1))
                if existing:
                    result = {"saved": True, "request_id": existing.id, "instruction": "The reported issue is already in the office queue. Do not duplicate it or promise a response time. Close briefly when appropriate."}
                    self.results[tool_id] = result
                    return result
                key = f"followup:{kind}:{self.turns.index(utterance)}"
                if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
                    event = self.event(db, call, kind, {"detail": detail, "caller_reply": text}, key)
                    db.add(m.Followup(call_id=call.id, kind=kind, owner="Mark" if kind == "complaint" else "Sarah",
                                      priority=0 if kind in {"urgent", "gas_emergency", "co_alarm"} else 1,
                                      detail=detail, requested=kind in {"callback", "lead"}))
                    db.flush()
                else:
                    event = None
                result = {"saved": True, "request_id": event.id if event else key, "instruction": "Request recorded only. No live transfer, notification or callback-time guarantee."}
        elif name == "finish_conversation":
            from brightwater.managed.boundaries import BOUNDARIES, business_request
            if self.understanding and self.understanding.meaning.control == "voicemail":
                from brightwater.campaign import voicemail_message_configured, voicemail_result
                if voicemail_message_configured(call):
                    if self.trusted_phone:
                        from brightwater.managed.semantic_runtime import finish_phone_voicemail
                        result = finish_phone_voicemail(db, call, self.understanding)
                        self.closed = True
                        return {'stopped': True, 'gateway_voicemail': True,
                                'gateway_message': result['approved_message']}
                    return voicemail_result(db, call, self.understanding)
            if self.understanding and self.understanding.meaning and self.understanding.meaning.control in BOUNDARIES:
                if business_request(self.understanding.meaning):
                    return {'finished': False, 'instruction': 'Continue the genuine enquiry, follow-up or arrangement request. Give emergency advice immediately where needed; do not issue a conduct warning or terminate for frustration.'}
                if self.understanding.meaning.control in {'automated_menu', 'voicemail'}:
                    return {'finished': False, 'instruction': 'Automation evidence is uncertain or not current. Do not disclose account details, press keys or issue a conduct warning. Clarify once whether a person can speak; do not enter a repeated automated dialogue.'}
                return {"finished": False, "instruction": "Do not end this call yet. Your next spoken reply MUST briefly explain the Brightwater purpose AND explicitly say that continuing unrelated or personal remarks will end this call. A generic offer to help without that conditional warning is insufficient. Resume any genuine enquiry, complaint or booking. Swearing about service is not abuse."}
            svc.finalise(db, call, ("Customer reminder conversation completed; outcome derives from saved database facts." if call.purpose == "campaign" else "Managed attended engineering phone conversation completed; outcome derives from saved database facts.") if self.trusted_phone else "Managed engineering evaluation completed. Business outcome derives from saved database facts; no phone call was made.")
            self.closed = True
            result = {"finished": True, "outcome": call.outcome}
        else:
            raise Rejected("unknown_tool", "Unsupported managed tool", 422)
        self.results[tool_id] = result
        return result

    def followup_detail(self, db, call, text, kind):
        if kind != 'callback':
            return text[:1500]
        # Keep the assent as evidence, with the business context Sarah needs.
        # Telephone context comes from original authenticated observer events,
        # not an LLM-supplied summary or provider-rewritten transcript.
        if self.trusted_phone:
            rows = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
                m.CallEvent.kind.in_(['user_utterance', 'agent_utterance'])).order_by(
                    m.CallEvent.occurred_at, m.CallEvent.received_at)))
            turns = [{'role': 'agent' if e.kind == 'agent_utterance' else 'user',
                      'text': e.payload.get('text', '')} for e in rows
                     if e.payload.get('source') == 'plivo_elevenlabs_observer'
                     and (e.kind == 'user_utterance' and e.payload.get('speech_timing_verified') is True
                          or e.kind == 'agent_utterance' and e.payload.get('playback_completed') is True
                          and e.payload.get('interrupted') is False)]
        else:
            turns = [t for t in self.turns if not t.get('interrupted')]
        failures = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
            m.CallEvent.kind == 'managed_tool_result').order_by(m.CallEvent.occurred_at.desc()).limit(12)))
        errors = list(dict.fromkeys(e.payload['result']['error'] for e in failures
                      if isinstance(e.payload.get('result'), dict) and e.payload['result'].get('error')))
        context = '\n'.join(('Caller: ' if t['role'] == 'user' else 'Agent: ') + t['text'][:180]
                            for t in turns[-6:])
        from brightwater.arrangements import current
        status = current(db, call)
        header = ('Office help requested. Caller reply: ' + text[:250]
                  + '\nBooking status: ' + status['status']
                  + ('; saved booking ' + status['booking_id'] if status.get('saved') else '; no saved booking'))
        if errors:
            header += '\nTool failures: ' + ', '.join(errors[:4])
        return (header + '\nRecent conversation (quoted, not booking confirmation):\n' + context)[:1500]

    def followup_requested(self, text, kind):
        evidence = self.understanding
        if not (evidence and evidence.call_id == self.call_id and evidence.reply.strip() == text.strip()
                and evidence.allows_followup(kind, previously_declined=self.callback_previously_declined)):
            return False
        if evidence.meaning.followup_basis == "contextual":
            previous = self.previous_agent()
            return bool(previous and not previous["interrupted"] and ' '.join(previous["text"].split()).casefold()
                        == ' '.join(evidence.question.split()).casefold())
        return True

    def confirm(self, db, call, proposal_id):
        recovery = self.readbacks.setdefault(proposal_id, {})
        if recovery.get("failed_readbacks", 0) >= 2:
            raise Rejected("booking_unavailable", "No booking was saved. Stop repeating the details or requesting another yes. Explain briefly that you cannot complete it right now; offer office help only if requested.")
        try:
            return self._confirm(db, call, proposal_id)
        except Rejected as error:
            previous = self.previous_agent()
            # Count distinct substantial readback attempts, not brief questions,
            # interruptions, or retries of the same caller turn. The save still
            # requires the complete, current, actually heard readback.
            attempt = len(self.turns)
            incomplete = (error.code in {"readback_incomplete", "confirmation_required"}
                          and previous and not previous["interrupted"] and len(previous["text"].split()) >= 35)
            if (incomplete or error.code == "browser_readback_interrupted") and recovery.get("last_failed_turn") != attempt:
                recovery["last_failed_turn"] = attempt
                recovery["failed_readbacks"] = recovery.get("failed_readbacks", 0) + 1
                if recovery["failed_readbacks"] >= 2:
                    raise Rejected("booking_unavailable", "No booking was saved. Stop repeating the details or requesting another yes. Explain briefly that you cannot complete it right now; offer office help only if requested.") from None
            raise

    def _confirm(self, db, call, proposal_id):
        svc.verified(call)
        from brightwater.managed.intent import require_confirmation
        if self.intent is None:
            raise Rejected("interpretation_unavailable", "The current appointment request could not be interpreted. No booking was saved; do not request another yes.")
        require_confirmation(self.intent)
        if self.trusted_phone:
            from brightwater.managed.phone import commit
            return commit(db, call, proposal_id, self.latest_user()["text"] if self.latest_user() else "", consent=self.intent, understanding=self.understanding)
        proposal = db.scalar(select(m.Proposal).where(m.Proposal.id == proposal_id).with_for_update())
        if not proposal or proposal.call_id != call.id:
            raise Rejected("proposal_not_found", "Prepare the booking first")
        existing = db.scalar(select(m.Booking).where(m.Booking.proposal_id == proposal.id))
        if existing:
            if existing.state != "confirmed":
                raise Rejected("booking_cancelled", "This arrangement was cancelled; prepare a fresh proposal")
            return {"confirmed": True, "booking_id": existing.id}
        expected = self.readbacks.get(proposal_id)
        # Browser roleplays use provider turn order. PSTN bookings use the
        # independently checked speech and carrier playback path above.
        if not self.text_only and call.purpose != "browser_simulation":
            raise Rejected("managed_audio_unqualified", "Voice booking confirmation is not qualified; use the text evaluation to validate booking integration")
        user = self.latest_user()
        previous = self.previous_agent()
        if (call.purpose == "browser_simulation" and expected and previous and previous["interrupted"]
            and self.turns.index(previous) >= expected.get("turn_index", len(self.turns))):
            raise Rejected("browser_readback_interrupted",
                "The booking details were cut off before they finished. The booking is not saved.")
        if (not expected or "turn_index" not in expected or not user or not previous or self.turns[-1] is not user
            or previous["interrupted"] or not self.intent.confirms(call.id, proposal, user["text"])
            or not semantic_readback(self.understanding, proposal, previous["text"])
            or self.turns.index(previous) < expected["turn_index"]):
            raise Rejected("confirmation_required", "Repeat the full current readback and wait for a fresh clear affirmative")
        if proposal.expires_at < now() or proposal.state != "prepared":
            raise Rejected("proposal_expired", "Prepare and confirm a fresh proposal")
        if db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.kind.in_(["gas_emergency", "co_alarm", "urgent"])).limit(1)):
            raise Rejected("unsafe_service_booking", "Urgent or emergency issues need human follow-up")
        self.event(db, call, "managed_confirmation", {"proposal_id": proposal.id, "fingerprint": proposal.fingerprint,
                   "contract": "browser_simulation_ordered_turns" if call.purpose == "browser_simulation" else "text_only_ordered_turns", "readback": previous["text"], "affirmative": user["text"],
                   "speech_timing_verified": False})
        booking = svc.reserve(db, call, proposal)
        return {"confirmed": True, "booking_id": booking.id, "total_pence": booking.total_pence,
                "evaluation_only": True}


def run_tool(conversation, name, args, tool_id):
    from brightwater.managed.gateway import broker
    from brightwater.managed.semantic_runtime import snapshot
    from brightwater.managed.understanding import interpret
    with Session(lab_engine()) as evidence_db:
        call = evidence_db.get(m.Call, conversation.call_id)
        current = snapshot(evidence_db, call, conversation=conversation, proposal_id=args.get("proposal_id"))
    conversation.understanding = interpret(current, redis=broker())
    conversation.callback_previously_declined = current['callback_previously_declined']
    conversation.intent = conversation.understanding.appointment_evidence() if current['proposal_id'] else None
    with Session(lab_engine(), expire_on_commit=False) as db, db.begin():
        try:
            with db.begin_nested():
                return conversation.execute(db, name, args, tool_id)
        except ValidationError as error:
            return parameter_error(error)
        except Rejected as error:
            return arrangement_error(db, db.get(m.Call, conversation.call_id), error, agreement_present=bool(conversation.intent and conversation.intent.decision == "confirm"))


def parameter_error(error):
    # Return actionable field paths, never Pydantic's raw input/PII/context.
    fields = sorted({'.'.join(str(part) for part in item['loc']) for item in error.errors(include_input=False, include_context=False, include_url=False)})
    tenant_phone = any(field.startswith('tenants.') and field.endswith('.phone') for field in fields)
    return {"error": "invalid_parameters", "invalid_fields": fields, "confirmed": False, "saved": False,
        "availability_changed": False, "customer_confirmation_needed": False,
        "instruction": ("No booking was saved and this result does not mean the slot is unavailable. Preserve the selected offer. "
            + ("For a landlord, obtain the missing tenant contact with an international phone number including country code; never invent a country code. For a homeowner use tenants=[]. " if tenant_phone else "Correct only the listed tool fields using the account and returned offer. ")
            + "Do not claim dates changed, ask for another booking yes, or collect homeowner tenant contacts. Retry only after correcting these fields.")}


def arrangement_error(db, call, error, *, agreement_present=False):
    result = managed_error(error, agreement_present=agreement_present)
    if call.identity_verified and error.code in {"intent_question", "intent_change", "readback_incomplete", "confirmation_required", "browser_readback_interrupted", "proposal_expired", "capacity_conflict", "offer_changed", "engineer_changed", "booking_already_saved"}:
        from brightwater.arrangements import current
        result["arrangement"] = current(db, call)
        if error.code == "browser_readback_interrupted":
            proposal = db.scalar(select(m.Proposal).where(m.Proposal.call_id == call.id,
                m.Proposal.state == "prepared").order_by(m.Proposal.created_at.desc()).limit(1))
            if proposal:
                result["readback"] = readback_text(proposal)
            result["instruction"] = ("Say: ‘The booking details were cut off. Please wait until I finish the question, then answer.’ "
                "Then say the returned readback exactly once, including the arrival hours and payment, and wait for a new reply. "
                "Do not offer new dates or treat the earlier yes as permission.")
        elif error.code in {"readback_incomplete", "confirmation_required"}:
            result["instruction"] = "Nothing was saved. Preserve the selected arrangement. Answer outstanding questions first, then give one complete concise readback and await a fresh reply. Do not search for new dates or ask for special words."
        elif error.code == "intent_question":
            result["instruction"] = "Answer the whole question from these actual arrangement facts first. Keep the selected date; do not search again or save until the caller has heard the full current details and authorises them."
    return result


def managed_error(error, *, agreement_present=False):
    unavailable = error.code in {"managed_audio_unqualified", "intent_unavailable", "intent_decline", "intent_cancel", "booking_cancelled", "booking_unavailable", "interpretation_unavailable"}
    pending = error.code == "evidence_pending"
    if error.code.startswith("intent_") or error.code in {"booking_cancelled", "booking_unavailable", "interpretation_unavailable"}:
        instruction = error.message
    elif unavailable:
        instruction = (("The customer has already given agreement. " if agreement_present else "")
            + "This channel cannot save the reservation. Never ask them to say yes again or suggest their answer was unclear. "
            "Explain briefly that no booking was saved and you cannot save it right now. Do not mention channels, audio evidence or internal qualification. "
            "Offer an office request once only if they want one; do not record a callback without their request.")
    else:
        instruction = error.message
    return {"error": error.code, "confirmed": False, "saved": False,
            "retryable": not unavailable, "customer_confirmation_needed": not (unavailable or pending) and error.code in {"readback_incomplete", "confirmation_required", "browser_readback_interrupted"},
            "caller_agreed": agreement_present, "instruction": instruction}
