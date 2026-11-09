"""Per-person security boundaries exercised through the real API and PostgreSQL."""
import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from conftest import make_call
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select
from test_bookings import confirmation

from brightwater import models as m
from brightwater import schemas as s
from brightwater import services as svc
from brightwater.api import app
from brightwater.config import settings
from brightwater.db import session
from brightwater.policy import now
from brightwater.staff import password_hash, password_matches

client = TestClient(app)
PASSWORD = "Test-only-personal-password-123"


@pytest.fixture
def staff():
    redis = Redis.from_url(settings().redis_url.get_secret_value())
    # Clear only this test suite's namespaced authentication counters.
    for pattern in ("bw:staff-login:*", "bw:staff-source:*", "bw:staff-password:*"):
        keys = list(redis.scan_iter(pattern))
        if keys:
            redis.delete(*keys)
    with session() as db, db.begin():
        for username, role, engineer in [("mark", "admin", None), ("samudra", "admin", None), ("sarah", "office", None), ("dan", "engineer", "dan"), ("priya", "engineer", "priya"), ("tom", "engineer", "tom")]:
            db.add(m.StaffUser(username=username, name=username.title(), role=role, engineer_id=engineer,
                               password_hash=password_hash(PASSWORD), change_required=False))


def login(username, password=PASSWORD):
    return client.post("/v1/auth/login", json={"username": username, "password": password})


def headers(username):
    response = login(username)
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_password_hash_and_session_storage(staff):
    a, b = password_hash(PASSWORD), password_hash(PASSWORD)
    assert a != b and PASSWORD not in a and password_matches(PASSWORD, a)
    assert not password_matches("wrong", a)
    result = login("mark").json()
    assert result["token"].startswith("bwstaff_")
    with session() as db:
        stored = db.scalar(select(m.StaffSession))
        assert stored.token_hash == hashlib.sha256(result["token"].encode()).hexdigest()
        assert stored.expires_at > now() + timedelta(hours=7)
    assert "password_hash" not in str(result)


def test_initial_password_blocks_business_access_and_revokes_sessions(staff):
    with session() as db, db.begin():
        db.get(m.StaffUser, "sarah").change_required = True
    auth = headers("sarah")
    assert client.get("/v1/auth/me", headers=auth).json()["change_required"] is True
    assert client.get("/v1/dashboard", headers=auth).status_code == 403
    assert client.get("/v1/staff", headers=auth).status_code == 403
    new = "New-test-only-personal-password"
    assert client.post("/v1/auth/password", headers=auth, json={"current_password": PASSWORD, "new_password": new}).status_code == 200
    assert client.get("/v1/auth/me", headers=auth).status_code == 401
    assert login("sarah").status_code == 401
    updated = {"Authorization": "Bearer " + login("sarah", new).json()["token"]}
    assert client.get("/v1/dashboard", headers=updated).status_code == 200


@pytest.mark.parametrize("username", ["dan", "priya", "tom"])
def test_engineers_cannot_read_or_mutate_office_data(staff, username):
    auth = headers(username)
    for path in ("/v1/customers", "/v1/calls", "/v1/calls/unknown", "/v1/calls/unknown/recording", "/v1/engineering/status", "/v1/quality", "/v1/staff", "/metrics"):
        assert client.get(path, headers=auth).status_code == 403, path
    for path, payload in [("/v1/control/pause", {}), ("/v1/calls", {"customer_id":"BW-1041", "request_key":"staff-denial"}), ("/v1/engineering/calls", {"request_key":m.uid()}), ("/v1/staff/sarah", {"action":"disable"})]:
        assert client.post(path, headers=auth, json=payload).status_code == 403, path


def test_engineer_dashboard_contains_only_own_assigned_jobs(staff):
    with session() as db, db.begin():
        for engineer, customer in [("dan", "BW-1041"), ("priya", "BW-1072")]:
            call, _ = make_call(db, customer_id=customer)
            prop = customer + "-P1"
            window = db.scalar(select(m.DiaryWindow).where(m.DiaryWindow.engineer_id == engineer, m.DiaryWindow.used_minutes <= 120).limit(1))
            offer = m.AvailabilityOffer(call_id=call.id, expires_at=now()+timedelta(minutes=5), items=[{
                "item_id":m.uid(), "property_id":prop, "service":"service", "window_id":window.id,
                "day":window.day.isoformat(), "period":window.period, "engineer_id":engineer}])
            db.add(offer)
            db.flush()
            proposal = svc.prepare(db, call, offer.id, [s.Tenant(property_id=prop, name="Fixture", phone="+447911111111")])
            svc.commit(db, call.id, proposal.id, confirmation(db, call, proposal))
    for username in ("dan", "priya", "tom"):
        data = client.get("/v1/dashboard", headers=headers(username)).json()
        assert set(data) == {"appointments", "viewer"}
        assert all(job["engineer"].lower().startswith(username) for job in data["appointments"])
        assert len(data["appointments"]) == (0 if username == "tom" else 1)


def test_office_and_admin_permissions(staff):
    auth = headers("sarah")
    assert client.get("/v1/customers", headers=auth).status_code == 200
    assert client.get("/v1/calls", headers=auth).status_code == 200
    for path in ("/v1/staff", "/v1/engineering/status", "/v1/quality"):
        assert client.get(path, headers=auth).status_code == 403
    response = client.get("/v1/staff", headers=headers("mark"))
    assert response.status_code == 200 and len(response.json()) == 6
    assert "password_hash" not in response.text
    machine = {"Authorization": "Bearer " + settings().operator_token.get_secret_value()}
    assert client.get("/v1/staff", headers=machine).status_code == 401


def test_reset_disable_and_logout_revoke_sessions(staff):
    admin = headers("mark")
    auth = headers("dan")
    temp = "Temporary-test-password-12345"
    assert client.post("/v1/staff/dan", headers=admin, json={"action":"reset_password", "temporary_password":temp}).status_code == 200
    assert client.get("/v1/auth/me", headers=auth).status_code == 401
    assert login("dan").status_code == 401
    assert login("dan", temp).json()["user"]["change_required"] is True
    auth = headers("sarah")
    assert client.post("/v1/staff/sarah", headers=admin, json={"action":"disable"}).status_code == 200
    assert client.get("/v1/auth/me", headers=auth).status_code == 401
    assert login("sarah").status_code == 401
    assert client.post("/v1/staff/sarah", headers=admin, json={"action":"enable"}).status_code == 200
    auth = headers("sarah")
    assert client.post("/v1/auth/logout", headers=auth).status_code == 200
    assert client.get("/v1/auth/me", headers=auth).status_code == 401
    assert client.post("/v1/staff/mark", headers=admin, json={"action":"disable"}).status_code == 409


def test_expired_forged_and_legacy_sessions_rejected(staff):
    auth = headers("mark")
    with session() as db, db.begin():
        db.scalar(select(m.StaffSession)).expires_at = now() - timedelta(seconds=1)
    for h in [auth, {"Authorization":"Bearer bwstaff_" + secrets.token_urlsafe(32)}, {"Authorization":"Basic b2ZmaWNlOnBhc3N3b3Jk"}]:
        assert client.get("/v1/dashboard", headers=h).status_code == 401


def test_login_rate_limit_generic_errors_and_failure_audit(staff):
    for _ in range(10):
        assert login("mark", "wrong").status_code == 401
    assert login("mark").status_code == 429
    assert login("does-not-exist", "wrong").json() == {"error":"unauthorised", "message":"Incorrect username or password"}
    with session() as db:
        assert len(db.scalars(select(m.StaffAudit).where(m.StaffAudit.action == "sign_in_failed")).all()) == 11


def test_login_fails_closed_when_rate_limiter_is_unavailable(staff, monkeypatch):
    def failed(*args, **kwargs):
        raise ConnectionError("test broker outage")
    monkeypatch.setattr(Redis, "eval", failed)
    assert login("mark").status_code == 503
    with session() as db:
        assert db.scalar(select(m.StaffSession)) is None


def test_concurrent_admin_disables_preserve_one_active_administrator(staff):
    auth = {name: headers(name) for name in ("mark", "samudra")}
    barrier = Barrier(2)

    def disable(actor, target):
        barrier.wait()
        return client.post("/v1/staff/" + target, headers=auth[actor], json={"action":"disable"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(disable, "mark", "samudra"), pool.submit(disable, "samudra", "mark")]
        results = [job.result(timeout=10) for job in jobs]
    assert sorted(results) == [200, 401]
    with session() as db:
        assert len(db.scalars(select(m.StaffUser).where(m.StaffUser.role == "admin", m.StaffUser.active.is_(True))).all()) == 1


def test_staff_audit_is_admin_only_and_contains_no_credentials(staff):
    admin = headers("mark")
    assert client.get("/v1/staff-audit", headers=headers("sarah")).status_code == 403
    assert client.get("/v1/staff-audit", headers=headers("tom")).status_code == 403
    response = client.get("/v1/staff-audit", headers=admin)
    assert response.status_code == 200
    assert response.json()[0]["action"] == "sign_in"
    assert PASSWORD not in response.text and "password_hash" not in response.text and "bwstaff_" not in response.text
