from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BW_", env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["local", "test", "staging", "showcase", "shadow", "production"] = "local"
    database_url: SecretStr
    redis_url: SecretStr
    operator_token: SecretStr
    runtime_token: SecretStr
    dialing_enabled: bool = False
    campaign_gateway_url: str = ""
    campaign_gateway_token: SecretStr = SecretStr("")
    campaign_route_verified: bool = False
    campaign_daily_limit: int = Field(default=20, ge=1, le=20)
    managed_campaign_agent_id: str = ""
    max_active_calls: int = Field(default=1, ge=1, le=20)
    livekit_url: str = ""
    livekit_api_key: SecretStr = SecretStr("")
    livekit_api_secret: SecretStr = SecretStr("")
    livekit_outbound_trunk_id: str = ""
    voice_agent_name: str = "brightwater"
    voice_pipeline: Literal["livekit_inference", "direct"] = "direct"
    voice_direct_mode: Literal["realtime_text", "cascaded"] = "realtime_text"
    openai_api_key: SecretStr = SecretStr("")
    elevenlabs_api_key: SecretStr = SecretStr("")
    api_url: str = "http://127.0.0.1:8787"
    voice_stt_model: str = ""
    voice_llm_model: str = ""
    voice_tts_model: str = ""
    voice_id: str = ""
    voice_speed: float = Field(default=0.95, ge=0.7, le=1.2)
    voice_stability: float = Field(default=0.5, ge=0, le=1)
    voice_similarity: float = Field(default=0.75, ge=0, le=1)
    voice_speaker_boost: bool = True
    voice_preemptive_generation: bool = False
    recording_notice: str = ""
    office_callback_number: str = ""
    voice_gateway_url: str = ""
    voice_gateway_token: SecretStr = SecretStr("")
    engineering_enabled: bool = False
    engineering_recipient: SecretStr = SecretStr("")
    engineering_callback_number: SecretStr = SecretStr("")
    engineering_consent_reference: str = ""
    engineering_display_name: str = "Samudra"
    engineering_call_limit: int = Field(default=3, ge=1, le=1000, description="Privately authorised lifetime attempt total; historical requests are never reset")
    managed_interpretation_model: Literal["gpt-4.1", "gpt-4.1-mini"] = "gpt-4.1"
    managed_enabled: bool = False
    managed_evaluation_request_limit: int = Field(default=10, ge=1, le=20)
    managed_phone_enabled: bool = False
    managed_phone_agent_id: str = ""
    managed_agent_id: str = ""
    managed_api_key: SecretStr = SecretStr("")
    managed_webhook_secret: SecretStr = SecretStr("")
    managed_database_url: SecretStr = SecretStr("")
    release_id: str = "development"
    replacement_quote_age_years: int = Field(default=15, ge=1, le=50)
    proposal_ttl_seconds: int = 120
    media_root: Path = Path("/tmp/brightwater-media")
    media_encryption_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_isolation(self):
        for field in ("operator_token", "runtime_token"):
            if len(getattr(self, field).get_secret_value()) < 32:
                raise ValueError(f"{field} must contain at least 32 characters")
        if self.operator_token == self.runtime_token:
            raise ValueError("Operator and runtime credentials must be distinct")
        if self.environment in {"shadow", "showcase", "test"} and self.dialing_enabled:
            raise ValueError(f"Dialing is forbidden in {self.environment}")
        if self.dialing_enabled:
            from brightwater.campaign import configuration_issues
            issues = configuration_issues(self)
            if issues:
                raise ValueError("Customer campaign is not ready: " + "; ".join(issues))
        if self.media_encryption_key.get_secret_value():
            from cryptography.fernet import Fernet
            try:
                Fernet(self.media_encryption_key.get_secret_value().encode())
            except (ValueError, TypeError) as error:
                raise ValueError("Media encryption key must be a valid Fernet key") from error
        if self.dialing_enabled and not self.media_encryption_key.get_secret_value():
            raise ValueError("Recording requires an independent media encryption key")
        if self.dialing_enabled:
            from brightwater.policy import Rejected, uk_phone
            try:
                uk_phone(self.office_callback_number)
            except Rejected as error:
                raise ValueError("Configure an approved real UK office callback number before dialing") from error
        if self.environment not in {"local", "test"} and not self.api_url.startswith("https://"):
            raise ValueError("Deployed runtime API traffic requires HTTPS")
        if self.engineering_enabled:
            import re
            if self.environment in {"shadow", "showcase", "test"}:
                raise ValueError("Engineering calls are forbidden in this environment")
            if not re.fullmatch(r"\+91[6-9]\d{9}", self.engineering_recipient.get_secret_value()):
                raise ValueError("Engineering recipient must be an explicitly consented Indian mobile")
            if not self.voice_gateway_url.startswith("https://") or len(self.voice_gateway_token.get_secret_value()) < 32:
                raise ValueError("Engineering calls require an authenticated HTTPS voice gateway")
            if len(self.engineering_consent_reference) < 20:
                raise ValueError("Engineering calls require recorded recipient authorisation")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
