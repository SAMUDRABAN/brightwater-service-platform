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
