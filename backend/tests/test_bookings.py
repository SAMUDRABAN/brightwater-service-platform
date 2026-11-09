from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest
from conftest import make_call
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.db import session
from brightwater.policy import Rejected, now


def prepare_offer(db, call, property_ids, window_id, service="service"):
    offer = m.AvailabilityOffer(call_id=call.id, expires_at=now() + timedelta(minutes=5), items=[
        {"item_id": m.uid(), "property_id": p, "service": service, "window_id": window_id,
         "day": "2026-11-16", "period": "MORNING", "engineer_id": "dan"} for p in property_ids])
    db.add(offer)
    db.flush()
    tenants = [s.Tenant(property_id=p, name="Assessment tenant", phone="+447911111111") for p in property_ids]
    return svc.prepare(db, call, offer.id, tenants)


def confirmation(db, call, proposal, interrupted=False, utterance="yes please"):
    start = datetime.now(UTC)
    svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind="readback_completed", occurred_at=start,
        payload={"proposal_id": proposal.id, "fingerprint": proposal.fingerprint}))
    if interrupted:
        svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind="interruption", occurred_at=start + timedelta(milliseconds=1)))
    return svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind="user_utterance",
        occurred_at=start + timedelta(milliseconds=2), payload={"text": utterance, "speech_timing_verified": True})).id


@pytest.mark.parametrize('utterance', ['Yeah, please do it.', 'Yeah, yeah, do it.'])
@pytest.mark.parametrize('interrupted', [False, True])
def test_actual_handset_booking_phrases_keep_readback_gate(utterance, interrupted):
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ['BW-1041-P1'], window.id)
        event_id = confirmation(db, call, proposal, interrupted=interrupted, utterance=utterance)
        if interrupted:
            with pytest.raises(Rejected), db.begin_nested():
                svc.commit(db, call.id, proposal.id, event_id)
            assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
        else:
            assert svc.commit(db, call.id, proposal.id, event_id).id


@pytest.mark.parametrize('timing', [False, None])
def test_backend_booking_rejects_missing_or_unverified_speech_timing(timing):
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ['BW-1041-P1'], window.id)
        event_id = confirmation(db, call, proposal)
        event = db.get(m.CallEvent, event_id)
        event.payload = {'text': 'yes please'} | ({'speech_timing_verified': timing} if timing is not None else {})
        db.flush()
        with pytest.raises(Rejected, match='affirmative'), db.begin_nested():
            svc.commit(db, call.id, proposal.id, event_id)
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


def test_atomic_landlord_booking_price_and_idempotent_replay():
    with session() as db, db.begin():
        call, _ = make_call(db, "BW-1056")
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, [f"BW-1056-P{i}" for i in range(1, 4)], window.id, "cp12")
        assert proposal.total_pence == 18000
        event_id = confirmation(db, call, proposal)
        first = svc.commit(db, call.id, proposal.id, event_id)
        replay = svc.commit(db, call.id, proposal.id, event_id)
        assert first.id == replay.id
        assert window.used_minutes == 180
        assert db.scalar(select(func.count()).select_from(m.BookingItem)) == 3


def test_interrupted_readback_needs_fresh_confirmation():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        event_id = confirmation(db, call, proposal, interrupted=True)
        with pytest.raises(Rejected, match="Repeat"):
            svc.commit(db, call.id, proposal.id, event_id)
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


def test_a_later_correction_invalidates_an_earlier_yes():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        event_id = confirmation(db, call, proposal)
        source = db.get(m.CallEvent, event_id)
        svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind="user_utterance",
            occurred_at=source.occurred_at + timedelta(milliseconds=1), payload={"text": "Actually, Thursday instead"}))
        with pytest.raises(Rejected) as result:
            svc.commit(db, call.id, proposal.id, event_id)
        assert result.value.code == "confirmation_superseded"


def test_no_confirmation_no_booking():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        with pytest.raises(Rejected, match="affirmative"):
            svc.commit(db, call.id, proposal.id, "nonexistent")


def test_landlord_missing_tenant_contact_rejected():
    with session() as db, db.begin():
        call, _ = make_call(db, "BW-1056")
        result = svc.availability(db, call, [s.ServiceItem(property_id="BW-1056-P1", service="cp12")])
        with pytest.raises(Rejected, match="Tenant"):
            svc.prepare(db, call, result["options"][0]["offer_id"], [])


def test_capacity_after_due_date_is_not_offered_as_suitable():
    with session() as db, db.begin():
        call, _ = make_call(db)
        obligation = db.scalar(select(m.Obligation).where(m.Obligation.property_id == "BW-1041-P1"))
        obligation.due_date = date(2026, 11, 15)
        db.flush()
        result = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="service")])
        assert result["options"] == []


def test_urgent_issue_blocks_routine_service():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        proposal = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        event_id = confirmation(db, call, proposal)
        svc.record_event(db, call.id, s.EventInput(provider_event_id=m.uid(), kind="urgent", occurred_at=datetime.now(UTC), payload={"detail": "No heating"}))
        with pytest.raises(Rejected):
            svc.commit(db, call.id, proposal.id, event_id)


def test_two_calls_race_for_last_hour_exactly_one_wins():
    work = []
    with session() as db, db.begin():
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 120).limit(1))
        window_id = window.id
        for customer_id in ["BW-1041", "BW-1107"]:
            call, _ = make_call(db, customer_id)
            proposal = prepare_offer(db, call, [customer_id + "-P1"], window_id)
            work.append((call.id, proposal.id, confirmation(db, call, proposal)))
    barrier = Barrier(2)

    def run(args):
        with session() as db:
            barrier.wait(timeout=5)
            try:
                with db.begin():
                    svc.commit(db, *args)
                return "committed"
            except Rejected as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, work))
    assert sorted(results) == ["capacity_conflict", "committed"]
    with session() as db:
        assert db.get(m.DiaryWindow, window_id).used_minutes == 180
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 1


def test_readback_of_another_proposal_invalidates_old_proposal():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        old = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        confirmation(db, call, old)
        new = prepare_offer(db, call, ["BW-1041-P1"], window.id)
        current_yes = confirmation(db, call, new)
        with pytest.raises(Rejected) as result:
            svc.commit(db, call.id, old.id, current_yes)
        assert result.value.code == "readback_superseded"
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
