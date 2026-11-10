from datetime import date

import pytest
from conftest import make_call
from sqlalchemy import func, select

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.arrangements import current
from brightwater.db import session
from brightwater.policy import Rejected


def free(db, day=date(2026, 11, 23), period="AFTERNOON", engineer="priya"):
    window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.day == day,
        m.DiaryWindow.period == period, m.DiaryWindow.engineer_id == engineer))
    assert window
    window.used_minutes = 0
    db.flush()
    return window


def selected(db, call, **preferences):
    result = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="service")], **preferences)
    assert result["options"]
    return result["options"][0]


def test_actual_named_engineer_date_and_window_are_returned_and_honoured():
    with session() as db, db.begin():
        call, _ = make_call(db)
        free(db)
        result = selected(db, call, preferred_day=date(2026, 11, 23), preferred_period="AFTERNOON", engineer_id="priya")
        assert not result["reserved"]
        assert result["items"][0]["engineer_id"] == "priya"
        assert result["items"][0]["engineer_name"] == db.get(m.Engineer, "priya").name
        assert result["items"][0]["day"] == "2026-11-23"
        assert result["items"][0]["period"] == "AFTERNOON"
        proposal = svc.prepare(db, call, result["offer_id"], [])
        details = current(db, call)
        assert details["status"] == "prepared" and not details["saved"]
        assert details["proposal_id"] == proposal.id
        assert details["items"][0]["engineer_name"] == "Priya Shah"


@pytest.mark.parametrize("engineer", ["tom", "mark", "unknown-engineer"])
def test_ineligible_or_unknown_engineer_is_not_silently_substituted(engineer):
    with session() as db, db.begin():
        call, _ = make_call(db)
        with pytest.raises(Rejected, match="cannot carry out"):
            selected(db, call, engineer_id=engineer)
        assert db.scalar(select(func.count()).select_from(m.AvailabilityOffer)) == 0


def test_no_space_for_named_preference_does_not_return_a_different_engineer():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = free(db)
        window.used_minutes = window.capacity_minutes
        free(db, engineer="dan")
        result = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="service")],
            preferred_day=window.day, preferred_period=window.period, engineer_id="priya")
        assert not result["options"]


def test_later_dates_and_repeated_reads_keep_actual_offers_stable():
    with session() as db, db.begin():
        call, _ = make_call(db)
        first = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="service")], after_day=date(2026, 11, 20))
        repeat = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="service")], after_day=date(2026, 11, 20))
        assert first["options"] == repeat["options"]
        assert all(i["day"] > "2026-11-20" for o in first["options"] for i in o["items"])
        assert db.scalar(select(func.count()).select_from(m.AvailabilityOffer)) == 2
        p = svc.prepare(db, call, first["options"][0]["offer_id"], [])
        assert svc.prepare(db, call, first["options"][0]["offer_id"], []).id == p.id
        assert db.scalar(select(func.count()).select_from(m.Proposal)) == 1


def test_requested_service_uses_its_own_due_date():
    with session() as db, db.begin():
        call, _ = make_call(db)
        db.add(m.Obligation(id="unrelated-old-cp12", property_id="BW-1041-P1", service="cp12", due_date=date(2026, 1, 1)))
        free(db)
        assert selected(db, call, preferred_day=date(2026, 11, 23))["items"]
        result = svc.availability(db, call, [s.ServiceItem(property_id="BW-1041-P1", service="cp12")])
        assert result["options"] == []


def test_landlord_can_use_morning_and_afternoon_on_the_same_day():
    with session() as db, db.begin():
        call, _ = make_call(db, "BW-1056")
        morning = free(db, period="MORNING")
        afternoon = free(db)
        morning.used_minutes = 120
        afternoon.used_minutes = 60
        result = svc.availability(db, call, [s.ServiceItem(property_id=f"BW-1056-P{i}", service="cp12") for i in range(1, 4)],
            preferred_day=date(2026, 11, 23), engineer_id="priya")
        assert len(result["options"]) == 1
        items = result["options"][0]["items"]
        assert len(items) == 3 and {i["day"] for i in items} == {"2026-11-23"}
        assert {i["period"] for i in items} == {"MORNING", "AFTERNOON"}
        tenants = [s.Tenant(property_id=i["property_id"], name="Fictional tenant", phone="+447911111111") for i in items]
        proposal = svc.prepare(db, call, result["options"][0]["offer_id"], tenants)
        assert proposal.total_pence == 18000


def test_changed_engineer_between_offer_and_save_requires_fresh_agreement():
    with session() as db, db.begin():
        call, _ = make_call(db)
        window = free(db)
        offer = selected(db, call, preferred_day=window.day, preferred_period=window.period, engineer_id="priya")
        proposal = svc.prepare(db, call, offer["offer_id"], [])
        db.add(m.Engineer(id="cover-gas", name="Fictional cover engineer", gas_registered=True, active=True))
        db.flush()
        window.engineer_id = "cover-gas"
        db.flush()
        with pytest.raises(Rejected, match="assignment changed"):
            svc.reserve(db, call, proposal)
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0
        assert window.used_minutes == 0


def test_a_finished_proposal_is_not_reported_as_a_booking():
    with session() as db, db.begin():
        call, _ = make_call(db)
        offer = selected(db, call)
        proposal = svc.prepare(db, call, offer["offer_id"], [])
        call.state = "finished"
        value = current(db, call)
        assert value["status"] == "not_booked" and not value["saved"] and not value["reserved"]
        assert value["proposal_id"] == proposal.id


def test_call_readmodel_and_voice_success_reference_the_same_saved_engineer():
    from datetime import timedelta

    from semantic_fixture import bind
    from test_managed_phone import event, phone

    from brightwater.api import call_detail
    from brightwater.policy import now

    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        at = now() - timedelta(seconds=2)
        event(db, call, "agent_utterance", at, source="plivo_elevenlabs_observer",
              text=prepared["readback"], playback_completed=True, interrupted=False)
        event(db, call, "user_utterance", at + timedelta(seconds=1), source="plivo_elevenlabs_observer",
              text="That works, book it please", speech_timing_verified=True)
        conv.agent(prepared["readback"])
        conv.user("That works, book it please")
        bind(db, conv, appointment="confirm")
        result = conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, "save")
        details = call_detail(call.id, db)
        assert details["arrangement"] == result["arrangement"]
        assert details["arrangement"]["saved"] is True
        assert details["arrangement"]["booking_id"] == result["booking_id"]
        item = details["arrangement"]["items"][0]
        window = db.scalar(select(m.DiaryWindow).join(m.BookingItem).where(m.BookingItem.booking_id == result["booking_id"]))
        assert item["engineer_id"] == window.engineer_id
        assert item["engineer_name"] == db.get(m.Engineer, window.engineer_id).name
        assert window.used_minutes >= 60
        assert len(details["bookings"]) == 1
        # A repeated preparation cannot create a second reservation in this call.
        assert conv.execute(db, "prepare_booking", {"offer_id": "unused", "tenants": []}, "repeat")["booking_id"] == result["booking_id"]


def test_short_booking_questions_do_not_exhaust_the_readback_recovery_budget():
    from semantic_fixture import bind
    from test_managed_phone import event, phone

    from brightwater.managed.engine import arrangement_error
    from brightwater.policy import now

    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        for attempt in range(3):
            conv.agent("Would you still like that appointment?")
            conv.user("Yes, please arrange it")
            event(db, call, "user_utterance", now(), source="plivo_elevenlabs_observer", text=conv.latest_user()["text"], speech_timing_verified=True)
            bind(db, conv, appointment="confirm")
            with pytest.raises(Rejected) as error:
                conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, str(attempt))
            assert error.value.code == "readback_incomplete"
            result = arrangement_error(db, call, error.value, agreement_present=True)
            assert result["arrangement"]["proposal_id"] == prepared["proposal_id"]
            assert not result["arrangement"]["saved"]
        assert conv.readbacks[prepared["proposal_id"]].get("failed_readbacks", 0) == 0


def test_engineer_question_overrides_assent_without_saving_or_researching_dates():
    from semantic_fixture import bind
    from test_managed_phone import event, phone

    from brightwater.managed.engine import arrangement_error
    from brightwater.policy import now

    with session() as db, db.begin():
        call, conv, prepared = phone(db)
        conv.agent(prepared["readback"])
        conv.user("Yeah I would, can I choose a specific engineer if you tell me their full names?")
        event(db, call, "user_utterance", now(), source="plivo_elevenlabs_observer", text=conv.latest_user()["text"], speech_timing_verified=True)
        bind(db, conv, appointment="question", appointment_target="current")
        with pytest.raises(Rejected) as error:
            conv.execute(db, "confirm_booking", {"proposal_id": prepared["proposal_id"]}, "question")
        result = arrangement_error(db, call, error.value)
        assert result["error"] == "intent_question" and not result["customer_confirmation_needed"]
        assert result["arrangement"]["proposal_id"] == prepared["proposal_id"]
        assert conv.readbacks[prepared["proposal_id"]].get("failed_readbacks", 0) == 0
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


def test_landlord_separate_days_still_form_one_discounted_proposal():
    with session() as db, db.begin():
        call, _ = make_call(db, "BW-1056")
        for window in db.scalars(select(m.DiaryWindow)):
            window.used_minutes = window.capacity_minutes
        for day in [23, 24, 25]:
            free(db, date(2026, 11, day)).used_minutes = 120
        db.flush()
        items = [s.ServiceItem(property_id=f"BW-1056-P{i}", service="cp12") for i in range(1, 4)]
        assert not svc.availability(db, call, items)["options"]
        separate = svc.availability(db, call, items, same_day=False)["options"]
        assert len(separate) == 1
        assert len({i["day"] for i in separate[0]["items"]}) == 3
        tenants = [s.Tenant(property_id=i.property_id, name="Fictional tenant", phone="+447911111111") for i in items]
        proposal = svc.prepare(db, call, separate[0]["offer_id"], tenants)
        assert proposal.total_pence == 18000 and len(proposal.items) == 3
