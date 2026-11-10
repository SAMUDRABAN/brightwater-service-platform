from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DestinationInput(Strict):
    phone: str
    consent_reference: str = Field(min_length=10, max_length=300)


class CallInput(Strict):
    customer_id: str
    request_key: str = Field(min_length=8, max_length=160)


class EngineeringCallInput(Strict):
    request_key: str = Field(min_length=8, max_length=160)


class EventInput(Strict):
    provider_event_id: str = Field(min_length=1, max_length=160)
    kind: Literal[
        "connected", "user_utterance", "agent_utterance", "turn_state", "identity_assertion", "speaker_changed",
        "readback_completed", "interruption", "gas_emergency", "co_alarm",
        "urgent", "complaint", "callback", "lead", "not_interested", "serviced_elsewhere",
        "wrong_number", "not_available", "voicemail", "no_answer", "busy", "failed", "ended",
    ]
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value


class ServiceItem(Strict):
    property_id: str
    service: Literal["service", "cp12", "combined"]


class AvailabilityInput(Strict):
    same_day: bool = True
    items: list[ServiceItem] = Field(min_length=1, max_length=20)
    preferred_day: date | None = None
    preferred_period: Literal["MORNING", "AFTERNOON"] | None = None
    engineer_id: str | None = Field(default=None, max_length=40)
    after_day: date | None = None


class Tenant(Strict):
    property_id: str
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(pattern=r"^\+[1-9]\d{6,14}$")


class PrepareInput(Strict):
    offer_id: str
    tenants: list[Tenant] = Field(default_factory=list)


class CommitInput(Strict):
    proposal_id: str
    confirmation_event_id: str


class SuppressInput(Strict):
    utterance_event_id: str


class FinishInput(Strict):
    summary: str = Field(min_length=20, max_length=1500)


class FollowupInput(Strict):
    kind: Literal["callback", "urgent", "gas", "complaint", "lead", "internal_review"]
    event_id: str
    detail: str = Field(min_length=10, max_length=1500)
    requested: bool = False


class CampaignAdmission(Strict):
    call_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    session_token: SecretStr
    phone: SecretStr
