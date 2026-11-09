from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_call
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.db import session
from brightwater.policy import Rejected

AT = datetime(2026, 11, 5, 12, tzinfo=UTC)


def test_manual_request_is_idempotent_and_serializes_shared_destination():
    with session() as db, db.begin():
        svc.register_destination(db, "BW-1041", "+447911123456", "Offline test consent reference")
        first = svc.request_call(db, "BW-1041", "idempotent-request", at=AT)
        replay = svc.request_call(db, "BW-1041", "idempotent-request", at=AT)
        assert replay.id == first.id
        assert db.scalar(select(func.count()).select_from(m.Outbox)) == 1
        svc.register_destination(db, "BW-1107", "+447911123456", "Offline test consent reference")
        with pytest.raises(Rejected, match="unresolved"):
            svc.request_call(db, "BW-1107", "different-customer-request", at=AT)


def test_cancelled_undialled_intent_does_not_consume_attempt_ordinal():
    with session() as db, db.begin():
        svc.register_destination(db, "BW-1041", "+447911123456", "Offline test consent reference")
        first = svc.request_call(db, "BW-1041", "first-undialled-request", at=AT)
        first.state = "cancelled"
        db.flush()
        second = svc.request_call(db, "BW-1041", "second-undialled-request", at=AT)
        assert second.attempt == 1


def test_three_dispatched_attempts_prevent_a_fourth():
    with session() as db, db.begin():
        dest = svc.register_destination(db, "BW-1041", "+447911123456", "Offline test consent reference")
        for n, band in enumerate(["morning", "midday", "afternoon"], 1):
            db.add(m.Call(customer_id="BW-1041", destination_id=dest.id, year=2026, attempt=n,
                          request_key=m.uid(), state="finished", time_band=band,
                          dispatched_at=AT - timedelta(days=6 - n)))
        db.flush()
        with pytest.raises(Rejected) as error:
            svc.request_call(db, "BW-1041", "fourth-call-request", at=AT.replace(hour=18))
        assert error.value.code == "attempts_exhausted"


def test_late_complaint_enriches_existing_final_outcome_without_duplicate_record():
    with session() as db, db.begin():
        call, _ = make_call(db)
        svc.finalise(db, call, "The call ended early. No arrangement was completed.")
        end_time = call.ended_at
        svc.record_event(db, call.id, s.EventInput(provider_event_id="late-complaint", kind="complaint",
            occurred_at=end_time - timedelta(seconds=1), payload={"detail": "Customer complained before disconnect"}))
        assert call.outcome == "Complaint"
        assert call.ended_at == end_time
        assert call.summary == "The call ended early. No arrangement was completed."
        assert db.scalar(select(func.count()).select_from(m.Call)) == 1


def test_redis_redelivery_cannot_start_a_disabled_real_call():
    from brightwater.worker import dispatch
    with session() as db, db.begin():
        svc.register_destination(db, "BW-1041", "+447911123456", "Offline test consent reference")
        call = svc.request_call(db, "BW-1041", "worker-redelivery-request", at=AT)
        db.flush()
        outbox = db.scalar(select(m.Outbox).where(m.Outbox.aggregate_id == call.id))
        outbox_id, call_id = outbox.id, call.id
    dispatch.run(outbox_id)
    dispatch.run(outbox_id)
    with session() as db:
        value = db.get(m.Call, call_id)
        assert value.state == "cancelled" and value.dispatched_at is None
        assert db.scalar(select(func.count()).select_from(m.Call)) == 1


@pytest.mark.parametrize("text", ["I'm Helen Price's daughter", "Speaking on behalf of Helen Price"])
def test_relative_mentioning_named_customer_cannot_unlock_account(text):
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        utterance = svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
            kind="user_utterance", occurred_at=AT, payload={"text": text}))
        with pytest.raises(Rejected, match="identity"):
            svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
                kind="identity_assertion", occurred_at=AT + timedelta(seconds=1),
                payload={"utterance_event_id": utterance.id}))
        assert not call.identity_verified


def test_speaker_handoff_requires_new_self_identification():
    with session() as db, db.begin():
        call, _ = make_call(db, verified=False)
        utterance = svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
            kind="user_utterance", occurred_at=AT, payload={"text": "Helen Price speaking"}))
        svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
            kind="speaker_changed", occurred_at=AT + timedelta(seconds=1)))
        with pytest.raises(Rejected, match="identity"):
            svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
                kind="identity_assertion", occurred_at=AT + timedelta(seconds=2),
                payload={"utterance_event_id": utterance.id}))
        fresh = svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
            kind="user_utterance", occurred_at=AT + timedelta(seconds=3), payload={"text": "Yes, speaking"}))
        svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(),
            kind="identity_assertion", occurred_at=AT + timedelta(seconds=4),
            payload={"utterance_event_id": fresh.id}))
        assert call.identity_verified


def test_active_call_admission_defers_queue_without_consuming_an_attempt(monkeypatch):
    from brightwater.worker import cfg, dispatch
    monkeypatch.setattr(cfg, "dialing_enabled", True)
    monkeypatch.setattr(cfg, "max_active_calls", 1)
    with session() as db, db.begin():
        make_call(db, "BW-1041")
        db.get(m.Control, "dialing").enabled = True
        svc.register_destination(db, "BW-1107", "+447911654321", "Offline consent fixture; no dial")
        queued = svc.request_call(db, "BW-1107", "admission-hold-request", at=AT)
        event = db.scalar(select(m.Outbox).where(m.Outbox.aggregate_id == queued.id))
        event_id, call_id = event.id, queued.id
    dispatch.run(event_id)
    with session() as db:
        call, event = db.get(m.Call, call_id), db.get(m.Outbox, event_id)
        assert call.state == "queued" and call.dispatched_at is None
        assert event.delivered_at is None and event.error == "waiting_for_admission"
