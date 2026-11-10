"""Build language snapshots from trusted events and prefetch without SQL locks."""
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.config import settings
from brightwater.db import engine
from brightwater.managed.boundaries import BOUNDARIES, terminal_reason
from brightwater.managed.readback import complete_readback
from brightwater.managed.understanding import interpret, snapshot_digest
from brightwater.policy import Rejected, explicit_opt_out, explicit_recording_refusal, now


def snapshot(db, call, *, conversation=None, proposal_id=None):
    if conversation is not None and not conversation.trusted_phone and call.purpose not in {"managed_evaluation", "browser_simulation"}:
        raise Rejected("managed_closed", "Evaluation session is absent, expired or closed", 403)
    person = db.get(m.Customer, call.customer_id)
    phone = call.purpose in {'engineering', 'campaign'}
    rows = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id).order_by(
        m.CallEvent.occurred_at, m.CallEvent.received_at)))
    if phone:
        user = next((e for e in reversed(rows) if e.kind == 'user_utterance'
                     and e.payload.get('source') == 'plivo_elevenlabs_observer'), None)
        if not user:
            raise Rejected('evidence_pending', 'The existing reply is still being matched; do not request a repeat')
        reply = user.payload.get('text', '')
        if conversation and (not conversation.latest_user() or conversation.latest_user()['text'].strip() != reply.strip()):
            raise Rejected('evidence_pending', 'The current reply has not arrived in the observer yet')
        speech = next((e for e in reversed(rows) if e.kind == 'agent_utterance'
                       and e.payload.get('source') == 'plivo_elevenlabs_observer'
                       and e.occurred_at < user.occurred_at), None)
        completed = bool(speech and speech.payload.get('playback_completed') is True and speech.payload.get('interrupted') is False)
        speech_text = speech.payload.get('text', '') if completed else ''
        source_id, playback_id = user.id, speech.id if speech else ''
        history = [{'role': 'agent' if e.kind == 'agent_utterance' else 'user', 'text': e.payload.get('text', ''), 'interrupted': bool(e.payload.get('interrupted')), 'completed': e.payload.get('playback_completed') is True}
                   for e in rows if e.kind in {'agent_utterance', 'user_utterance'} and e.occurred_at <= user.occurred_at][-8:]
    else:
        user = conversation.latest_user() if conversation else None
        if not user:
            raise Rejected('evidence_required', 'No current caller reply is present')
        reply = user['text']
        position = conversation.turns.index(user)
        history = conversation.turns[max(0, position - 7):position + 1]
        previous = next((t for t in reversed(conversation.turns[:position]) if t['role'] == 'agent'), None)
        speech_text = previous['text'] if previous else ''
        source_id, playback_id = 'managed-turn:' + str(position), ''
        speech = None
    proposal = db.get(m.Proposal, proposal_id) if proposal_id else db.scalar(select(m.Proposal).where(
        m.Proposal.call_id == call.id).order_by(m.Proposal.created_at.desc()).limit(1))
    if proposal is not None and proposal.call_id != call.id:
        proposal = None
    previously_declined = any(e.kind == 'semantic_turn' and e.payload.get('followup') == 'decline_callback' and e.payload.get('source_event_id') != source_id for e in rows)
    return {'call_purpose': call.purpose, 'call_id': call.id, 'customer_name': person.name, 'reply': reply, 'question': speech_text,
            'source_id': source_id, 'playback_id': playback_id,
            'proposal_id': proposal.id if proposal else '', 'fingerprint': proposal.fingerprint if proposal else '',
            'history': history, 'completed_agent_speech': speech_text,
            'callback_previously_declined': previously_declined,
            'extract_readback': bool(proposal and speech_text and not complete_readback(speech_text, proposal)),
            'speech_completed': bool(speech and speech.payload.get('playback_completed') is True
                                     and speech.payload.get('interrupted') is False) if phone else bool(previous and not previous['interrupted'])}


def record_meaning(db, call, evidence):
    if evidence.meaning is None:
        return
    key = 'semantic-turn:' + evidence.digest
    if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
        meaning = evidence.meaning
        warning = ' '.join(meaning.boundary_warning_quote.split()).casefold()
        speech = db.get(m.CallEvent, evidence.playback_id) if len(warning) >= 20 else None
        grounded = bool(len(warning) >= 20 and speech and speech.call_id == call.id
            and speech.kind == 'agent_utterance' and speech.payload.get('source') == 'plivo_elevenlabs_observer'
            and speech.payload.get('playback_completed') is True and speech.payload.get('interrupted') is False
            and warning in ' '.join(speech.payload.get('text', '').split()).casefold()
            and warning in ' '.join(evidence.question.split()).casefold())
        db.add(m.CallEvent(call_id=call.id, provider_event_id=key, kind='semantic_turn', occurred_at=now(),
            payload={'source': 'server_semantic_turn', 'digest': evidence.digest,
                     'source_event_id': evidence.source_id, 'playback_event_id': evidence.playback_id,
                     'identity': meaning.identity, 'followup': meaning.followup, 'control': meaning.control,
                     'boundary_warning_grounded': grounded,
                     'appointment': meaning.appointment, 'disposition': meaning.disposition, 'model': settings().managed_interpretation_model}))
        db.flush()
    if evidence.meaning.followup == 'urgent':
        source = db.get(m.CallEvent, evidence.source_id)
        if (call.purpose in {'engineering', 'campaign'} and source and source.call_id == call.id
            and source.kind == 'user_utterance' and source.payload.get('source') == 'plivo_elevenlabs_observer'
            and source.payload.get('speech_timing_verified') is True and source.payload.get('text', '').strip() == evidence.reply.strip()
            and timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
            key = 'reported-urgent:' + source.id
            if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
                svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind='urgent',
                    occurred_at=source.occurred_at, payload={'source': 'server_semantic_turn', 'detail': evidence.reply[:1500]}))
    if evidence.meaning.control == 'voicemail' and terminal_reason(db, call, evidence) == 'voicemail':
        key = 'voicemail-detected:' + call.id
        if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id,
            m.CallEvent.provider_event_id == key)):
            svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind='voicemail',
                occurred_at=now(), payload={'source': 'verified_caller_automation',
                    'source_event_id': evidence.source_id, 'message_delivered': False}))
    disposition = evidence.meaning.disposition
    if disposition != 'none' and (disposition == 'not_available' or call.identity_verified):
        if call.purpose == 'browser_simulation':
            source = db.scalar(select(m.CallEvent).where(m.CallEvent.call_id == call.id,
                m.CallEvent.provider_event_id == evidence.source_id, m.CallEvent.kind == 'user_utterance'))
            if source and source.payload.get('text') == evidence.reply:
                key = 'browser-disposition:' + source.id
                if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id,
                    m.CallEvent.provider_event_id == key)):
                    svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind=disposition,
                        occurred_at=source.occurred_at, payload={'source': 'browser_simulation', 'utterance_event_id': source.id}))
            return
        source = db.get(m.CallEvent, evidence.source_id)
        if (call.purpose in {'engineering', 'campaign'} and source and source.call_id == call.id
            and source.kind == 'user_utterance' and source.payload.get('source') == 'plivo_elevenlabs_observer'
            and source.payload.get('speech_timing_verified') is True and source.payload.get('text', '').strip() == evidence.reply.strip()
            and timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
            key = 'disposition:' + source.id
            if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
                svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind=disposition,
                    occurred_at=source.occurred_at, payload={'source': 'server_semantic_turn', 'utterance_event_id': source.id}))
                if disposition != 'not_available':
                    svc.stop_campaign(db, call)


def apply_control(db, call, evidence):
    """Only trusted current caller data can stop or revoke access; no model write args."""
    if evidence.meaning is None or evidence.meaning.control == 'none':
        return False
    if evidence.meaning.control == 'voicemail':
        from brightwater.campaign import voicemail_message_configured
        if voicemail_message_configured(call):
            return False
    if evidence.meaning.control in BOUNDARIES:
        reason = terminal_reason(db, call, evidence)
        if not reason:
            return False
        key = 'boundary-end:' + evidence.source_id
        if not db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
            db.add(m.CallEvent(call_id=call.id, provider_event_id=key, kind='turn_state', occurred_at=now(),
                payload={'source': 'boundary_terminal_requested', 'reason': reason,
                         'source_event_id': evidence.source_id, 'model': settings().managed_interpretation_model}))
        svc.finalise(db, call, 'Call ended politely: ' + reason + '. Existing saved actions are retained; no new callback was inferred.')
        return True
    person = db.get(m.Customer, call.customer_id)
    if not evidence.matches(call.id, person.name, evidence.reply):
        raise Rejected('interpretation_mismatch', 'The current reply needs a fresh interpretation')
    source = db.get(m.CallEvent, evidence.source_id)
    if call.purpose in {'engineering', 'campaign'} and (not source or source.call_id != call.id
        or source.kind != 'user_utterance' or source.payload.get('source') != 'plivo_elevenlabs_observer'
        or source.payload.get('text', '').strip() != evidence.reply.strip()
        or not timedelta(0) <= now() - source.occurred_at <= timedelta(seconds=30)):
        raise Rejected('evidence_pending', 'The current caller reply is still being checked')
    if source is None:
        source = m.CallEvent(call_id=call.id, provider_event_id='semantic-source:' + evidence.digest,
            kind='user_utterance', occurred_at=now(), payload={'text': evidence.reply, 'source': 'managed_text_semantic',
                                                           'speech_timing_verified': False})
        db.add(source)
        db.flush()
    control = evidence.meaning.control
    key = 'semantic-control:' + evidence.source_id + ':' + control
    if db.scalar(select(m.CallEvent.id).where(m.CallEvent.call_id == call.id, m.CallEvent.provider_event_id == key)):
        return control != 'speaker_changed'
    if control == 'stop_calling':
        svc.suppress(db, call, source.id)
        call.identity_verified = False
        call.state, call.ended_at = 'finished', now()
        call.summary = 'The caller asked not to be contacted. Contact suppression was saved.'
    elif control == 'recording_refused':
        call.identity_verified = False
        svc.stop_campaign(db, call)
        call.state, call.ended_at = 'finished', now()
        call.summary = 'The caller declined recording. Further account access and actions were stopped.'
    elif control == 'wrong_number':
        call.identity_verified = False
        svc.record_event(db, call.id, s.EventInput(provider_event_id=key, kind='wrong_number', occurred_at=now(),
            payload={'source': 'server_semantic_turn', 'utterance_event_id': source.id}))
        call.state, call.ended_at = 'finished', now()
    elif control == 'speaker_changed':
        call.identity_verified = False
    if control != 'wrong_number':
        db.add(m.CallEvent(call_id=call.id, provider_event_id=key,
            kind=control if control in {'speaker_changed', 'recording_refused'} else 'semantic_control', occurred_at=source.occurred_at,
            payload={'source': 'server_semantic_turn', 'control': control, 'utterance_event_id': source.id}))
    if control != 'speaker_changed':
        svc.finalise(db, call, call.summary or 'The caller ended this contact; no new action was authorised.')
    return control != 'speaker_changed'


def prefetch(call_id, event_id):
    """API background task: caller inference overlaps native agent generation."""
    from brightwater.managed.gateway import broker
    try:
        backstop = False
        with Session(engine()) as db:
            call = db.get(m.Call, call_id)
            if (not call or call.purpose not in {'engineering', 'campaign'} or not settings().managed_phone_enabled):
                return
            source = db.get(m.CallEvent, event_id)
            if (not source or source.call_id != call_id or source.kind != 'user_utterance'
                or source.payload.get('source') != 'plivo_elevenlabs_observer'):
                return
            text = source.payload.get('text', '')
            backstop = explicit_opt_out(text) or explicit_recording_refusal(text)
            if not backstop:
                if call.state != 'in_progress':
                    return
                current = snapshot(db, call)
                if current['source_id'] != event_id:
                    return
        if backstop:
            # Ingestion already saved suppression/refusal in the same transaction
            # as this trusted transcript. Close the admitted call even if inference
            # is unavailable. This fast backstop is additional to semantic control.
            with Session(engine()) as db, db.begin():
                svc.control_lock(db)
                call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
                if call and call.state == 'in_progress':
                    call.identity_verified = False
                    svc.finalise(db, call, 'The caller asked to stop this contact. No further account access was permitted.')
            if explicit_recording_refusal(text):
                stop_carrier(call_id)
            else:
                from brightwater.managed.closing import OPT_OUT
                stop_carrier(call_id, closing_message=OPT_OUT)
            return
        redis = broker()
        evidence = interpret(current, redis=redis)
        message = None
        with Session(engine()) as db, db.begin():
            svc.control_lock(db)
            call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
            if not call or call.state != 'in_progress':
                return
            latest = snapshot(db, call)
            # A model decision about an older turn cannot apply a new action.
            # Explicit opt-out backstops still run at event ingestion independently.
            if latest['source_id'] != event_id or snapshot_digest(latest) != evidence.digest:
                return
            record_meaning(db, call, evidence)
            if evidence.meaning.control == 'voicemail' and terminal_reason(db, call, evidence) == 'voicemail':
                result = finish_phone_voicemail(db, call, evidence)
                terminal, message = True, result['approved_message']
            else:
                terminal = apply_control(db, call, evidence)
        if terminal:
            control = evidence.meaning.control
            if control == 'stop_calling':
                from brightwater.managed.closing import OPT_OUT
                message = OPT_OUT
            stop_carrier(call_id, polite=control in BOUNDARIES - {'voicemail'}, closing_message=message)
    except Exception:
        # Cache/prefetch is not permission. The tool path must obtain and validate
        # a usable decision, or fail closed without requesting another yes.
        return


def finish_phone_voicemail(db, call, evidence):
    from brightwater.campaign import voicemail_result
    result = voicemail_result(db, call, evidence)
    svc.finalise(db, call, 'Voicemail detected. Message playback is recorded separately.')
    return result


def stop_carrier(call_id, *, polite=False, closing_message=None):
    """Only revoke an already admitted call; never admit, redial or change routing."""
    cfg = settings()
    if not cfg.voice_gateway_url or not cfg.voice_gateway_token.get_secret_value():
        return False
    payload = {'call_id': call_id, 'polite': polite}
    if closing_message:
        payload['closing_message'] = closing_message
    try:
        with httpx.Client(timeout=4, follow_redirects=False) as client:
            result = client.post(cfg.voice_gateway_url.rstrip('/') + '/v1/stop',
                headers={'Authorization': 'Bearer ' + cfg.voice_gateway_token.get_secret_value()},
                json=payload)
            result.raise_for_status()
        return True
    except Exception:
        return False


def prefetch_readback(call_id, event_id):
    from brightwater.managed.gateway import broker
    from brightwater.managed.understanding import extract_facts
    try:
        with Session(engine()) as db:
            call, speech = db.get(m.Call, call_id), db.get(m.CallEvent, event_id)
            if (not call or call.purpose not in {'engineering', 'campaign'} or call.state != 'in_progress'
                or not settings().managed_phone_enabled or not speech or speech.call_id != call_id):
                return
            completed = (speech.kind == 'agent_utterance'
                and speech.payload.get('source') == 'plivo_elevenlabs_observer'
                and speech.payload.get('playback_completed') is True
                and speech.payload.get('interrupted') is False)
            caption = (speech.kind == 'turn_state'
                and speech.payload.get('source') == 'managed_agent_prompt'
                and speech.payload.get('completed') is False)
            if not (completed or caption):
                return
            # Analysis of a caption is only a text-keyed cache warm-up. No event,
            # identity, proposal or booking is changed here. Commit still needs
            # actual completed carrier playback of this exact text and a fresh reply.
            proposal = db.scalar(select(m.Proposal).where(m.Proposal.call_id == call_id,
                m.Proposal.state == 'prepared').order_by(m.Proposal.created_at.desc()).limit(1))
            if not proposal or speech.occurred_at <= proposal.created_at:
                return
            text = speech.payload.get('text', '')
            if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                return
            if caption and len(text) < 80:
                return  # Avoid speculative model work for short lookup acknowledgements.
            if complete_readback(text, proposal):
                return
        extract_facts(text, redis=broker())
    except Exception:
        return
