import os
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from brightwater.config import Settings, settings
from brightwater.policy import Rejected, uk_phone
from brightwater.voice_agent import configure_provider_environment


def test_voice_inference_cannot_inherit_another_projects_credentials(monkeypatch):
    keys = ["LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_INFERENCE_API_KEY",
            "LIVEKIT_INFERENCE_API_SECRET"]
    for key in keys:
        monkeypatch.setenv(key, "another-project-placeholder")
    configure_provider_environment(SimpleNamespace(
        livekit_api_key=SecretStr("isolated-test-project-placeholder"),
        livekit_api_secret=SecretStr("isolated-test-secret-placeholder"),
    ))
    assert os.environ["LIVEKIT_API_KEY"] == os.environ["LIVEKIT_INFERENCE_API_KEY"] == "isolated-test-project-placeholder"
    assert os.environ["LIVEKIT_API_SECRET"] == os.environ["LIVEKIT_INFERENCE_API_SECRET"] == "isolated-test-secret-placeholder"


def test_invalid_provider_configuration_never_echoes_secret_inputs():
    values = settings().model_dump()
    sentinel = "do-not-log-provider-credential-sentinel"
    values.update(openai_api_key=sentinel, operator_token="short")
    with pytest.raises(ValidationError) as caught:
        Settings(**values)
    assert sentinel not in str(caught.value)
    assert "input_value" not in str(caught.value)


def test_indian_engineering_number_cannot_enter_uk_campaign_policy():
    with pytest.raises(Rejected) as caught:
        uk_phone("+919000000001")
    assert caught.value.code == "invalid_destination"
