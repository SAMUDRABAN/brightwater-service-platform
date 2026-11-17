"""Office workflows against real PostgreSQL, including permissions and immutable call facts."""

from datetime import time

import pytest
from conftest import make_call
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from test_staff import headers
from test_staff import staff as staff

from brightwater import models as m
from brightwater.api import app
from brightwater.config import settings
from brightwater.db import engine, session

client = TestClient(app)


def operator():
    return {"Authorization": "Bearer " + settings().operator_token.get_secret_value()}


def fixture(kind="callback"):
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.state, call.outcome, call.summary = (
            "finished",
            "Callback requested",
            "A fictional caller requested help with their annual service.",
        )
        f = m.Followup(
            call_id=call.id,
            kind=kind,
            owner="Sarah",
            priority=1,
            detail="Please call back in office hours",
            requested=True,
        )
        db.add(f)
        db.flush()
        return call.id, f.id


def test_followup_resolve_reopen_assign_is_audited_and_preserves_call_outcome(staff):
    call_id, followup = fixture()
    auth = headers("sarah")
    payload = {
        "action": "resolve",
        "note": "Spoke to the fictional customer and dealt with the enquiry.",
        "request_key": m.uid(),
    }
    for _ in range(2):
        r = client.post("/v1/office/followups/" + followup, headers=auth, json=payload)
        assert r.status_code == 200 and r.json()["resolved"]
    assert client.get("/v1/office/followups", headers=auth).json() == []
    assert len(client.get("/v1/office/followups?status=resolved", headers=auth).json()) == 1
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=auth,
            json=payload | {"note": "Different note"},
        ).status_code
        == 409
    )
    assert not client.post(
        "/v1/office/followups/" + followup,
        headers=auth,
        json={"action": "reopen", "request_key": m.uid()},
    ).json()["resolved"]
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=auth,
            json={"action": "assign", "owner": "Mark", "request_key": m.uid()},
        ).json()["owner"]
        == "Mark"
    )
    with session() as db:
        call = db.get(m.Call, call_id)
        assert call.outcome == "Callback requested" and call.state == "finished"
        audit = list(
            db.scalars(select(m.CallEvent).where(m.CallEvent.kind == "office_followup_updated"))
        )
        assert len(audit) == 3 and audit[0].payload["actor"] == "sarah"
        assert db.scalar(select(func.count()).select_from(m.Suppression)) == 0
        assert db.scalar(select(func.count()).select_from(m.Booking)) == 0


@pytest.mark.parametrize(
    "path",
    [
        "/v1/office/followups",
        "/v1/office/calls",
        "/v1/office/customers/BW-1041",
        "/v1/office/diary",
    ],
)
def test_crm_requires_authentication(path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("username", ["dan", "priya", "tom"])
def test_engineers_can_only_read_own_diary(staff, username):
    auth = headers(username)
    for path in ["/v1/office/followups", "/v1/office/calls", "/v1/office/customers/BW-1041"]:
        assert client.get(path, headers=auth).status_code == 403
    data = client.get("/v1/office/diary", headers=auth)
    assert data.status_code == 200 and all(w["engineer_id"] == username for w in data.json())
    assert (
        client.post(
            "/v1/office/customers/BW-1041/preferences", headers=auth, json={"not_before": "11:00"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/office/followups/" + m.uid(),
            headers=auth,
            json={"action": "resolve", "request_key": m.uid()},
        ).status_code
        == 403
    )


def test_office_can_see_customer_properties_and_change_preference_without_unsuppressing(staff):
    auth = headers("sarah")
    with session() as db, db.begin():
        db.add(
            m.Suppression(
                customer_id="BW-1056",
                phone="+447700900738",
                evidence="Fictional do-not-call fixture",
            )
        )
    response = client.get("/v1/office/customers/BW-1056", headers=auth)
    assert response.status_code == 200
    c = response.json()
    assert len(c["properties"]) == 3 and c["suppressed"]
    assert c["destination_hint"] is None and "source_phone" not in c
    assert (
        client.post(
            "/v1/office/customers/BW-1056/preferences", headers=auth, json={"not_before": "12:30"}
        ).status_code
        == 200
    )
    with session() as db:
        assert db.get(m.Customer, "BW-1056").not_before == time(12, 30)
        assert db.scalar(select(func.count()).select_from(m.Suppression)) == 1
    assert (
        client.post(
            "/v1/office/customers/BW-1056/preferences", headers=auth, json={"not_before": None}
        ).status_code
        == 200
    )
    assert client.get("/v1/office/customers/ENGINEERING-SAMUDRA", headers=auth).status_code == 403


@pytest.mark.parametrize("value", ["12:00:01", "12:00:00+01:00", "not-a-time"])
def test_preference_is_a_local_minute_not_an_ambiguous_offset(value):
    assert (
        client.post(
            "/v1/office/customers/BW-1041/preferences",
            headers=operator(),
            json={"not_before": value},
        ).status_code
        == 422
    )


def test_call_search_pagination_scope_and_sensitive_fields():
    with session() as db, db.begin():
        first, _ = make_call(db, "BW-1041")
        first.state, first.summary = "finished", "A 100% fictional result for review."
        second, _ = make_call(db, "BW-1072")
        second.purpose, second.state = "engineering", "finished"
    data = client.get("/v1/office/calls?page_size=1", headers=operator()).json()
    assert data["total"] == 2 and len(data["items"]) == 1
    second = client.get("/v1/office/calls?page_size=1&page=2", headers=operator()).json()
    assert data["items"][0]["id"] != second["items"][0]["id"]
    assert client.get("/v1/office/calls?scope=engineering", headers=operator()).json()["total"] == 1
    assert client.get("/v1/office/calls?q=Helen", headers=operator()).json()["total"] == 1
    assert client.get("/v1/office/calls?q=%25", headers=operator()).json()["total"] == 1
    assert not {"session_token_hash", "recording_key", "provider_id"} & set(data["items"][0])
    assert client.get("/v1/office/calls?page=0", headers=operator()).status_code == 422
    assert client.get("/v1/office/calls?page_size=101", headers=operator()).status_code == 422


def test_directory_scales_past_620_without_per_customer_queries():
    with session() as db, db.begin():
        db.add_all(
            [
                m.Customer(
                    id=f"BW-{2000 + i}",
                    name=f"Fictional contact {i}",
                    kind="homeowner",
                    source_phone="+447700900714",
                )
                for i in range(620)
            ]
        )
    queries = []

    def count(connection, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine(), "before_cursor_execute", count)
    try:
        result = client.get("/v1/customers", headers=operator())
    finally:
        event.remove(engine(), "before_cursor_execute", count)
    assert result.status_code == 200 and len(result.json()) == 628
    assert len(queries) <= 6, "Directory lookup must not add a query for each customer"


def test_complaints_cannot_be_reassigned_away_from_mark():
    _, followup = fixture("complaint")
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=operator(),
            json={"action": "assign", "owner": "Sarah", "request_key": m.uid()},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=operator(),
            json={"action": "assign", "owner": "Mark", "request_key": m.uid()},
        ).json()["owner"]
        == "Mark"
    )


def test_followup_assignment_requires_an_owner_and_rejects_extra_write_fields():
    _, followup = fixture()
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=operator(),
            json={"action": "assign", "request_key": m.uid()},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/office/followups/" + followup,
            headers=operator(),
            json={"action": "resolve", "request_key": m.uid(), "outcome": "Booked"},
        ).status_code
        == 422
    )


def test_booking_details_enforce_engineer_ownership_without_call_record_access(staff):
    from datetime import timedelta

    from test_bookings import confirmation

    from brightwater import schemas as s
    from brightwater import services as svc
    from brightwater.policy import now

    saved = {}
    with session() as db, db.begin():
        for engineer, customer in [("dan", "BW-1041"), ("priya", "BW-1072")]:
            call, _ = make_call(db, customer)
            window = db.scalar(
                select(m.DiaryWindow)
                .where(m.DiaryWindow.engineer_id == engineer, m.DiaryWindow.used_minutes <= 120)
                .limit(1)
            )
            offer = m.AvailabilityOffer(
                call_id=call.id,
                expires_at=now() + timedelta(minutes=5),
                items=[
                    {
                        "item_id": m.uid(),
                        "property_id": customer + "-P1",
                        "service": "service",
                        "window_id": window.id,
                        "day": window.day.isoformat(),
                        "period": window.period,
                        "engineer_id": engineer,
                    }
                ],
            )
            db.add(offer)
            db.flush()
            proposal = svc.prepare(
                db,
                call,
                offer.id,
                [
                    s.Tenant(
                        property_id=customer + "-P1", name="Fictional tenant", phone="+447700900714"
                    )
                ],
            )
            booking = svc.commit(db, call.id, proposal.id, confirmation(db, call, proposal))
            saved[engineer] = booking.id
    dan = headers("dan")
    result = client.get("/v1/office/bookings/" + saved["dan"], headers=dan)
    assert result.status_code == 200 and result.json()["call_id"] is None
    assert all(i["engineer"].startswith("Dan") for i in result.json()["items"])
    assert client.get("/v1/office/bookings/" + saved["priya"], headers=dan).status_code == 404
    assert (
        client.get("/v1/office/bookings/" + saved["dan"], headers=headers("tom")).status_code == 404
    )
    assert (
        client.get("/v1/office/bookings/" + saved["priya"], headers=headers("sarah")).status_code
        == 200
    )


def test_staff_can_resolve_unclassified_phone_outcome_with_evidence(staff):
    with session() as db, db.begin():
        call, _ = make_call(db)
        call.state = "finished"
        call_id = call.id
        db.add(m.Followup(call_id=call_id, kind="internal_review", owner="Sarah", priority=1, detail="Check the recording"))
    path = f"/v1/office/calls/{call_id}/outcome"
    payload = {"disposition": "wrong_number", "note": "The person answering confirmed the number belongs to somebody else."}
    assert client.post(path, headers=headers("dan"), json=payload).status_code == 403
    assert client.post(path, headers=headers("sarah"), json=payload | {"disposition": "Booked"}).status_code == 422
    for _ in range(2):
        response = client.post(path, headers=headers("sarah"), json=payload)
        assert response.status_code == 200
        assert response.json()["outcome"] == "Wrong number"
    assert client.post(path, headers=headers("sarah"), json=payload | {"disposition": "voicemail"}).status_code == 409
    with session() as db:
        assert db.get(m.Call, call_id).outcome == "Wrong number"
        notes = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call_id)))
        assert len(notes) == 1 and notes[0].payload["actor"] == "sarah"
        followups = {f.kind: f.resolved for f in db.scalars(select(m.Followup).where(m.Followup.call_id == call_id))}
        assert followups == {"internal_review": True, "wrong_number": False}


def test_office_call_scopes_keep_uk_and_browser_tests_out_of_campaign():
    scopes = ("campaign", "uk_test", "engineering", "browser_simulation")
    with session() as db, db.begin():
        for customer, scope in zip(("BW-1041", "BW-1072", "BW-1056", "BW-1107"), scopes, strict=True):
            call, _ = make_call(db, customer)
            call.state = "finished"
            if scope == "uk_test":
                call.time_band = scope
            else:
                call.purpose = scope
            db.add(m.Followup(call_id=call.id, kind="callback", owner="Sarah", priority=1, detail="Review"))
    for scope in scopes:
        calls = client.get(f"/v1/office/calls?scope={scope}", headers=operator()).json()["items"]
        followups = client.get(f"/v1/office/followups?scope={scope}", headers=operator()).json()
        assert [c["purpose"] for c in calls] == [scope]
        assert [f["purpose"] for f in followups] == [scope]
        assert calls[0]["id"] == followups[0]["call_id"]


def test_office_reschedule_and_cancel_preserve_call_and_apply_capacity_once(staff, monkeypatch):
    from datetime import UTC, datetime

    from test_bookings import confirmation, prepare_offer

    from brightwater import office, office_bookings
    from brightwater import services as svc

    reference = datetime(2026, 11, 15, 12, tzinfo=UTC)
    monkeypatch.setattr(office, "now", lambda: reference)
    monkeypatch.setattr(office_bookings, "now", lambda: reference)
    with session() as db, db.begin():
        call, _ = make_call(db)
        old, new, full = db.scalars(select(m.DiaryWindow)
            .where(m.DiaryWindow.engineer_id == "priya", m.DiaryWindow.used_minutes == 0)
            .order_by(m.DiaryWindow.day).limit(3)).all()
        proposal = prepare_offer(db, call, ["BW-1041-P1"], old.id)
        booking = svc.commit(db, call.id, proposal.id, confirmation(db, call, proposal))
        call.state, call.outcome, call.time_band = "finished", "Booked", "uk_test"
        old_id, target, booking_id, call_id = old.id, new.id, booking.id, call.id
        ineligible = db.scalar(select(m.DiaryWindow.id).where(m.DiaryWindow.engineer_id == "tom").limit(1))
        full.used_minutes = full.capacity_minutes
        full_id = full.id
    auth = headers("sarah")
    path = f"/v1/office/bookings/{booking_id}"
    before = client.get(path, headers=auth).json()
    assert before["purpose"] == "uk_test" and before["can_cancel"]
    appointment = client.get("/v1/dashboard", headers=auth).json()["appointments"][0]
    assert appointment["purpose"] == "uk_test"
    item = before["items"][0]
    assert target in {option["id"] for option in item["rescheduling_options"]}
    move = {"action": "reschedule", "request_key": m.uid(), "revision": before["revision"],
            "item_id": item["id"], "window_id": target, "note": "Customer agreed to a new window"}
    assert client.post(path, headers=headers("priya"), json=move).status_code == 403
    assert client.post(path, headers=auth, json=move | {"window_id": ineligible}).status_code == 422
    blocked = client.post(path, headers=auth, json=move | {"window_id": full_id})
    assert blocked.status_code == 409 and blocked.json()["error"] == "capacity_conflict"
    for _ in range(2):
        result = client.post(path, headers=auth, json=move)
        assert result.status_code == 200 and result.json()["state"] == "confirmed"
    moved = client.get(path, headers=auth).json()
    assert moved["revision"] != before["revision"] and moved["items"][0]["price_pence"] == 9500
    assert len(moved["history"]) == 1 and moved["history"][0]["actor"] == "sarah"
    with session() as db:
        assert db.get(m.DiaryWindow, old_id).used_minutes == 0
        assert db.get(m.DiaryWindow, target).used_minutes == 60
        assert db.scalar(select(m.BookingItem).where(m.BookingItem.booking_id == booking_id)).window_id == target

    cancel = {"action": "cancel", "request_key": m.uid(), "revision": before["revision"],
              "note": "Customer cancelled the visit"}
    assert client.post(path, headers=auth, json=cancel).json()["error"] == "booking_changed"
    cancel["revision"] = moved["revision"]
    for _ in range(2):
        result = client.post(path, headers=auth, json=cancel)
        assert result.status_code == 200 and result.json()["state"] == "cancelled"
    after = client.get(path, headers=auth).json()
    assert not after["can_cancel"] and len(after["history"]) == 2
    assert client.get("/v1/dashboard", headers=auth).json()["appointments"] == []
    with session() as db:
        assert db.get(m.DiaryWindow, target).used_minutes == 0
        assert db.get(m.Call, call_id).outcome == "Booked"
        due = db.scalar(select(m.Obligation).where(m.Obligation.property_id == "BW-1041-P1"))
        assert not due.resolved


def test_diary_lock_refreshes_previously_read_capacity():
    from brightwater import services as svc

    with session() as db, db.begin():
        window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.used_minutes == 0).limit(1))
        with session() as other, other.begin():
            other.get(m.DiaryWindow, window.id).used_minutes = 60
        locked = svc.lock_diary_windows(db, {window.id})
        assert locked[window.id] is window
        assert window.used_minutes == 60


def test_diary_explains_pre_existing_capacity_without_creating_visits(staff):
    auth = headers("dan")
    windows = client.get("/v1/office/diary", headers=auth).json()
    morning = next(w for w in windows if w["day"] == "2026-11-17" and w["period"] == "MORNING")
    assert morning["blocks"] == [{"kind": "pre_existing_work", "minutes": 180}]
    assert morning["used_minutes"] == morning["capacity_minutes"] == 180
    assert all(w["engineer_id"] == "dan" for w in windows)
    assert client.get("/v1/dashboard", headers=auth).json()["appointments"] == []


def test_call_results_keep_later_suppression_out_of_earlier_call(staff):
    from brightwater import schemas as s
    from brightwater import services as svc
    from brightwater.call_results import refresh_result
    from brightwater.policy import now

    with session() as db, db.begin():
        old, _ = make_call(db, "BW-1041", verified=False)
        later, _ = make_call(db, "BW-1072", verified=False)
        svc.record_event(db, later.id, s.EventInput(provider_event_id="stop", kind="user_utterance",
            occurred_at=now(), payload={"text": "Do not call me again"}))
        svc.finalise(db, later, "")
        assert later.outcome == "Do not call"
        old.state = "finished"
        refresh_result(db, old, [], historical=True)
        assert old.outcome == "No answer" and old.outcome_review_required
        assert "before any further contact" in old.summary
        call_id = old.id
    rows = client.get("/v1/office/calls?outcome=technical_review", headers=headers("sarah")).json()["items"]
    assert [row["id"] for row in rows] == [call_id]
    assert rows[0]["outcome"] == "No answer" and rows[0]["outcome_review_required"]


def test_office_can_create_customer_approve_number_and_schedule_without_dialling(staff, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from brightwater import office
    from brightwater.campaign import enqueue_due

    current = datetime(2026, 11, 17, 10, tzinfo=UTC)
    monkeypatch.setattr(office, "now", lambda: current)
    auth = headers("sarah")
    payload = {"request_key": m.uid(), "name": "Example customer", "kind": "homeowner",
               "address": "1 Fictional Street, Portsmouth, PO1 1AA", "phone": "07911 123456"}
    assert client.post("/v1/office/customers", headers=headers("dan"), json=payload).status_code == 403
    assert client.post("/v1/office/customers", headers=auth, json=payload | {
        "request_key": m.uid(), "phone": "07700 900714", "consent_reference": "Test fixture",
    }).json()["error"] == "fictional_destination"
    response = client.post("/v1/office/customers", headers=auth, json=payload)
    assert response.status_code == 201
    cid = response.json()["id"]
    assert client.post("/v1/office/customers", headers=auth, json=payload).json()["id"] == cid
    path = "/v1/office/customers/" + cid
    customer = client.get(path, headers=auth).json()
    assert customer["contact_phone"] == "+447911123456"
    assert not customer["destination_approved"] and len(customer["properties"]) == 1
    assert client.post("/v1/customers/" + cid + "/destination", headers=auth, json={
        "phone": "07911 123456", "consent_reference": "Offline customer consent; never dial",
    }).status_code == 200
    schedule = {"schedule_at": "2026-11-18T12:15"}
    assert client.post(path + "/schedule", headers=auth, json=schedule).json()["error"] == "no_reminder"
    reminder = {"property_id": customer["properties"][0]["id"], "service": "service", "due_date": "2026-12-28"}
    assert client.post(path + "/reminders", headers=auth, json=reminder).status_code == 201
    assert client.post(path + "/schedule", headers=auth, json={
        "schedule_at": "2026-11-22T12:15",
    }).json()["error"] == "outside_calling_window"
    assert client.post(path + "/schedule", headers=auth, json=schedule).status_code == 200
    assert client.get(path, headers=auth).json()["scheduled_call_at"].startswith("2026-11-18T12:15")
    assert client.post(path + "/schedule", headers=auth, json={"schedule_at": None}).json()["scheduled_call_at"] is None
    assert client.post(path + "/schedule", headers=auth, json=schedule).status_code == 200
    appointment = datetime(2026, 11, 18, 12, 15, tzinfo=UTC)
    with session() as db, db.begin():
        assert not db.get(m.Control, "dialing").enabled
        assert db.scalar(select(func.count()).select_from(m.Call)) == 0
        assert enqueue_due(db, appointment - timedelta(seconds=1)) == []
        queued = enqueue_due(db, appointment)
        assert len(queued) == 1
        call = db.get(m.Call, queued[0])
        assert call.customer_id == cid and call.state == "queued" and call.request_key.startswith("scheduled:")
        assert db.get(m.Customer, cid).scheduled_call_at is None
        assert enqueue_due(db, appointment) == []
        assert db.scalar(select(func.count()).select_from(m.Outbox)) == 1


def test_existing_due_customer_waits_for_scheduled_time_and_rechecks_suppression(staff, monkeypatch):
    from datetime import UTC, datetime

    from brightwater import office
    from brightwater import services as svc
    from brightwater.campaign import enqueue_due
    from brightwater.policy import Rejected

    at = datetime(2026, 11, 17, 11, tzinfo=UTC)
    monkeypatch.setattr(office, "now", lambda: at)
    cid = "BW-1107"
    phone = "+447911123456"
    with session() as db, db.begin():
        svc.register_destination(db, cid, phone, "Offline consent record; never dial")
    response = client.post("/v1/office/customers/" + cid + "/schedule", headers=headers("sarah"),
                           json={"schedule_at": "2026-11-18T12:15"})
    assert response.status_code == 200
    with session() as db, db.begin():
        assert enqueue_due(db, at) == []
        with pytest.raises(Rejected, match="Cancel or change"):
            svc.request_call(db, cid, "manual-request", at=at)
        db.add(m.Suppression(phone=phone, evidence="Test opt-out"))
        db.flush()
        assert enqueue_due(db, datetime(2026, 11, 18, 12, 15, tzinfo=UTC)) == []
        assert db.scalar(select(func.count()).select_from(m.Outbox)) == 0
