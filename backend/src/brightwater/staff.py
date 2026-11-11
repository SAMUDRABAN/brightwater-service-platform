"""Staff authentication. Passwords and raw session tokens are never persisted."""
import hashlib
import re
import secrets
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from brightwater import models as m
from brightwater.config import settings
from brightwater.db import get_db
from brightwater.policy import Rejected, now

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_db, scope="function")]

def engineer_allowed(method, path):
    return method == "GET" and (path in {"/v1/dashboard", "/v1/office/diary"} or bool(re.fullmatch(r"/v1/office/bookings/[a-f0-9-]{36}", path)))


def office_allowed(method, path):
    if method == "GET":
        if re.fullmatch(r"/v1/office/bookings/[a-f0-9-]{36}", path):
            return True
        return path in ("/v1/campaign/status", "/v1/dashboard", "/v1/customers", "/v1/calls", "/v1/office/followups", "/v1/office/calls", "/v1/office/diary") or bool(re.fullmatch(r"/v1/office/customers/BW-[0-9]{4}", path)) or bool(re.fullmatch(r"/v1/calls/[a-f0-9-]{36}(/recording)?", path))
    if method == "POST":
        if re.fullmatch(r"/v1/office/calls/[a-f0-9-]{36}/outcome", path):
            return True
        return path in ("/v1/calls", "/v1/control/pause") or bool(re.fullmatch(r"/v1/office/followups/[a-f0-9-]{36}", path)) or bool(re.fullmatch(r"/v1/office/customers/BW-[0-9]{4}/preferences", path)) or bool(re.fullmatch(r"/v1/customers/BW-[0-9]{4}/destination", path))
    return False


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=134217728).hex()
    return "scrypt-v1$" + salt + ":" + digest

def password_matches(password, encoded):
    if not encoded.startswith("scrypt-v1$"):
        return False
    salt, expected = encoded.removeprefix("scrypt-v1$").split(":")
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=134217728).hex()
    return secrets.compare_digest(actual, expected)

DUMMY = password_hash("unused-dummy-password")

def public(user):
    return {k: getattr(user, k) for k in ("username", "name", "role", "engineer_id", "active", "change_required")}

def principal(db, authorization):
    if not authorization or not authorization.startswith("Bearer bwstaff_") or len(authorization) > 150:
        raise Rejected("unauthorised", "Sign in required", 401)
    token = db.get(m.StaffSession, hashlib.sha256(authorization[7:].encode()).hexdigest())
    user = db.get(m.StaffUser, token.username) if token and token.expires_at > now() else None
    if not user or not user.active:
        raise Rejected("unauthorised", "Session expired or revoked", 401)
    return user

def identity(db: DB, authorization: str | None = Header(default=None)):
    return principal(db, authorization)

USER = Annotated[m.StaffUser, Depends(identity)]


def revoke(db, username):
    db.execute(delete(m.StaffSession).where(m.StaffSession.username == username))

def audit(db, username, action):
    db.add(m.StaffAudit(username=username, action=action))

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)

class Password(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=14, max_length=128)

class Update(BaseModel):
    action: Literal["reset_password", "enable", "disable"]
    temporary_password: str | None = Field(default=None, min_length=14, max_length=128)

def rate_limit(key, limit=10, seconds=900):
    try:
        redis = Redis.from_url(settings().redis_url.get_secret_value(), socket_timeout=2)
        attempts = redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n", 1, key, seconds)
    except Exception as exc:
        raise Rejected("unavailable", "Sign-in temporarily unavailable", 503) from exc
    if attempts > limit:
        raise Rejected("rate_limited", "Too many attempts. Please try again later", 429)
    return redis


@router.post("/auth/login")
def login(body: Login, request: Request, db: DB):
    username = body.username.strip().lower()
    key = "bw:staff-login:" + hashlib.sha256(username.encode()).hexdigest()
    rate_limit("bw:staff-source:" + hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest(), 180, 60)
    redis = rate_limit(key)
    user = db.get(m.StaffUser, username, with_for_update=True)
    matches = password_matches(body.password, user.password_hash if user else DUMMY)
    if not user or not user.active or not matches:
        audit(db, username, "sign_in_failed")
        return JSONResponse(status_code=401, content={"error": "unauthorised", "message": "Incorrect username or password"})
    redis.delete(key)
    db.execute(delete(m.StaffSession).where(m.StaffSession.username == username, m.StaffSession.expires_at <= now()))
    token = "bwstaff_" + secrets.token_urlsafe(32)
    db.add(m.StaffSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), username=username, expires_at=now()+timedelta(hours=8)))
    audit(db, username, "sign_in")
    return {"token": token, "user": public(user)}

@router.get("/auth/me")
def me(user: USER):
    return public(user)

@router.post("/auth/logout")
def logout(user: USER, db: DB, authorization: str = Header()):
    db.execute(delete(m.StaffSession).where(m.StaffSession.token_hash == hashlib.sha256(authorization[7:].encode()).hexdigest()))
    audit(db, user.username, "sign_out")
    return {"ok": True}

@router.post("/auth/password")
def change(body: Password, user: USER, db: DB):
    # Lock identity while changing credentials and invalidating concurrent sessions.
    rate_limit("bw:staff-password:" + user.username)
    db.refresh(user, with_for_update=True)
    if not password_matches(body.current_password, user.password_hash):
        raise Rejected("unauthorised", "Current password is incorrect", 401)
    if password_matches(body.new_password, user.password_hash):
        raise Rejected("invalid_password", "Choose a different password", 422)
    user.password_hash = password_hash(body.new_password)
    user.change_required = False
    revoke(db, user.username)
    audit(db, user.username, "password_changed")
    return {"ok": True}

def admin(user):
    if user.change_required or user.role != "admin":
        raise Rejected("forbidden", "Administrator access required", 403)

@router.get("/staff")
def team(user: USER, db: DB):
    admin(user)
    return [public(u) for u in db.scalars(select(m.StaffUser).order_by(m.StaffUser.name))]

@router.post("/staff/{username}")
def update(username: str, body: Update, user: USER, db: DB):
    admin(user)
    # Serialise administrative changes, including two administrators attempting
    # to disable one another. The acting administrator must remain active.
    list(db.scalars(select(m.StaffUser).where(m.StaffUser.role == "admin").order_by(m.StaffUser.username).with_for_update()))
    db.refresh(user)
    if not user.active:
        raise Rejected("unauthorised", "Session revoked", 401)
    target = db.get(m.StaffUser, username, with_for_update=True)
    if not target:
        raise Rejected("not_found", "Staff member not found", 404)
    if target.username == user.username:
        raise Rejected("self_change", "Use your own password settings; your account cannot be disabled here", 409)
    if body.action == "reset_password":
        if not body.temporary_password:
            raise Rejected("invalid_password", "Temporary password required", 422)
        target.password_hash = password_hash(body.temporary_password)
        target.change_required = True
    else:
        target.active = body.action == "enable"
    revoke(db, username)
    audit(db, user.username, body.action + ":" + username)
    return public(target)


@router.get("/staff-audit")
def audit_log(user: USER, db: DB):
    admin(user)
    return [{"id": event.id, "username": event.username, "action": event.action, "created_at": event.created_at}
            for event in db.scalars(select(m.StaffAudit).order_by(m.StaffAudit.created_at.desc()).limit(100))]
