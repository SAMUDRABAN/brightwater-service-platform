from datetime import date, datetime, time
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from brightwater.db import Base


def uid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    from datetime import UTC
    return datetime.now(UTC)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    source_phone: Mapped[str] = mapped_column(String(30))
    not_before: Mapped[time | None] = mapped_column(Time)
    notes: Mapped[str] = mapped_column(Text, default="")
    contact_blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    address: Mapped[str] = mapped_column(String(300))
    boiler: Mapped[str] = mapped_column(String(100), default="")
    boiler_year: Mapped[int | None] = mapped_column(Integer)


class Obligation(Base):
    __tablename__ = "obligations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    service: Mapped[str] = mapped_column(String(20))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Engineer(Base):
    __tablename__ = "engineers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    gas_registered: Mapped[bool] = mapped_column(Boolean)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DiaryWindow(Base):
    __tablename__ = "diary_windows"
    __table_args__ = (
        UniqueConstraint("engineer_id", "day", "period"),
        CheckConstraint("used_minutes >= 0 AND used_minutes <= capacity_minutes"),
        CheckConstraint("capacity_minutes > 0 AND capacity_minutes <= 180"),
        CheckConstraint("period IN ('MORNING', 'AFTERNOON')"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    engineer_id: Mapped[str] = mapped_column(ForeignKey("engineers.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(20))
    capacity_minutes: Mapped[int] = mapped_column(Integer, default=180)
    used_minutes: Mapped[int] = mapped_column(Integer, default=0)


class DiaryBlock(Base):
    __tablename__ = "diary_blocks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    window_id: Mapped[str] = mapped_column(ForeignKey("diary_windows.id"))
    minutes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(100))


class Destination(Base):
    __tablename__ = "destinations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), unique=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    consent_reference: Mapped[str] = mapped_column(String(300))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Suppression(Base):
    __tablename__ = "suppressions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True)
    evidence: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"
    __table_args__ = (UniqueConstraint("customer_id", "year"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    year: Mapped[int] = mapped_column(Integer)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    voicemail_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        Index("unique_dispatched_attempt", "customer_id", "year", "attempt", unique=True,
              postgresql_where=text("dispatched_at IS NOT NULL")),
        Index("one_active_customer_call", "customer_id", unique=True,
              postgresql_where=text("state IN ('queued','dispatching','unknown','in_progress')")),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"))
    year: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(20), default="campaign", server_default="campaign")
    request_key: Mapped[str] = mapped_column(String(160), unique=True)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    time_band: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    conversation: Mapped[bool] = mapped_column(Boolean, default=False)
    session_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    outcome: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(Text, default="")
    media_state: Mapped[str] = mapped_column(String(30), default="not_available")
    recording_key: Mapped[str | None] = mapped_column(String(500))
    release_id: Mapped[str] = mapped_column(String(100), default="development")


class CallEvent(Base):
    __tablename__ = "call_events"
    __table_args__ = (UniqueConstraint("call_id", "provider_event_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    provider_event_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    items: Mapped[list] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    total_pence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(30), default="prepared")
    operation_id: Mapped[str] = mapped_column(String(40), unique=True, default=uid)


class AvailabilityOffer(Base):
    __tablename__ = "availability_offers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    items: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), unique=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    total_pence: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BookingItem(Base):
    __tablename__ = "booking_items"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"))
    window_id: Mapped[str] = mapped_column(ForeignKey("diary_windows.id"))
    service: Mapped[str] = mapped_column(String(20))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_pence: Mapped[int] = mapped_column(Integer)
    tenant_name: Mapped[str | None] = mapped_column(String(160))
    tenant_phone: Mapped[str | None] = mapped_column(String(30))


class Followup(Base):
    __tablename__ = "followups"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    owner: Mapped[str] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text)
    requested: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    topic: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))


class QualityRun(Base):
    __tablename__ = "quality_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    release_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="not_evaluated")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Control(Base):
    __tablename__ = "controls"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class StaffUser(Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'office', 'engineer')", name="staff_role_valid"),
        CheckConstraint("role != 'engineer' OR engineer_id IS NOT NULL", name="staff_engineer_link"),
    )
    username: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    engineer_id: Mapped[str | None] = mapped_column(ForeignKey("engineers.id"))
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    change_required: Mapped[bool] = mapped_column(Boolean, default=True)


class StaffSession(Base):
    __tablename__ = "staff_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(ForeignKey("staff_users.username"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StaffAudit(Base):
    __tablename__ = "staff_audit"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
