"""Explicit semantic decisions for contract tests, not a phrase recogniser.

Classifier accuracy is evaluated separately against the real model. These helpers
exercise what the backend permits when given a particular typed interpretation.
"""
from brightwater import models as m
from brightwater.managed.semantic_runtime import snapshot
from brightwater.managed.understanding import Meaning, Understanding, snapshot_digest


def meaning(**changes):
    return Meaning(identity='unclear', identity_question=False, identity_question_quote='', identity_name_quote='', notice_complete=False,
        notice_quote='', followup='none', followup_basis='none', rescinds_callback_refusal=False,
        control='none', boundary_warning_quote='', disposition='none', appointment='unclear', appointment_target='none', readback=None).model_copy(update=changes)


def bind(db, conv, **decisions):
    call = db.get(m.Call, conv.call_id)
    current = snapshot(db, call, conversation=conv)
    if decisions.get("appointment") in {"confirm", "cancel"}:
        decisions.setdefault("appointment_target", "current")
    if decisions.get("identity_question"):
        decisions.setdefault("identity_question_quote", current["question"])
    if decisions.get("identity") == "self":
        decisions.setdefault("identity_name_quote", current["reply"])
    conv.understanding = Understanding(**{k: current[k] for k in (
        'call_id', 'customer_name', 'reply', 'question', 'source_id', 'playback_id', 'proposal_id', 'fingerprint')},
        digest=snapshot_digest(current), meaning=meaning(**decisions))
    conv.callback_previously_declined = current['callback_previously_declined']
    conv.intent = conv.understanding.appointment_evidence() if current['proposal_id'] else None
    return conv.understanding
