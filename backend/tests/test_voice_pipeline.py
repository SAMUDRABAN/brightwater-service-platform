"""Offline factory tests: real pinned SDK objects, no call/session/provider start."""

import asyncio
import json
import socket
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from brightwater.voice_pipeline import (
    DirectVoiceOptions,
    build_native_audio_lab_session,
    build_voice_session,
    voice_pipeline_manifest,
)


@pytest.fixture(autouse=True)
def database():
    """These pure factory tests do not use the application's database fixture."""
    yield


def options(**overrides):
    return DirectVoiceOptions(
        openai_api_key="test-openai-do-not-send",
        elevenlabs_api_key="test-eleven-do-not-send",
        stt_model="gpt-4o-mini-transcribe",
        llm_model="gpt-realtime",
        tts_model="eleven_flash_v2_5",
        voice_id="test-licensed-voice",
        **overrides,
    )


@pytest.fixture
def forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Factory construction must not make network requests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_manifest_and_options_do_not_disclose_keys():
    cfg = options()
    evidence = repr(cfg) + json.dumps(voice_pipeline_manifest(cfg))
    assert cfg.openai_api_key not in evidence
    assert cfg.elevenlabs_api_key not in evidence
    manifest = voice_pipeline_manifest(cfg)
    assert manifest["turn_detector"] == "local-v1-mini"
    assert manifest["interruption_min_words"] == 0
    assert manifest["qualification"].startswith("unmeasured")


@pytest.mark.parametrize("field", ["openai_api_key", "elevenlabs_api_key", "voice_id"])
def test_missing_configuration_fails_without_secret_echo(field):
    with pytest.raises(ValueError) as caught:
        replace(options(), **{field: ""})
    assert "test-openai" not in str(caught.value)
    assert "test-eleven" not in str(caught.value)


def test_model_architecture_mismatch_rejected():
    with pytest.raises(ValueError, match="realtime_text requires"):
        replace(options(), llm_model="gpt-4.1-mini")
    with pytest.raises(ValueError, match="cascaded requires"):
        replace(options(), mode="cascaded")
    with pytest.raises(ValueError, match="delay bounds"):
        replace(options(), endpoint_min_seconds=4, endpoint_max_seconds=2)


def test_settings_support_secretstr_without_environment_fallback(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-fallback")
    cfg = SimpleNamespace(
        openai_api_key=SecretStr("test-explicit"),
        elevenlabs_api_key=SecretStr("test-explicit-eleven"),
        voice_stt_model="gpt-4o-mini-transcribe",
        voice_llm_model="gpt-realtime",
        voice_tts_model="eleven_flash_v2_5",
        voice_id="voice",
        voice_direct_mode="realtime_text",
    )
    assert DirectVoiceOptions.from_settings(cfg).openai_api_key == "test-explicit"
    cfg.openai_api_key = SecretStr("")
    with pytest.raises(ValueError, match="openai_api_key"):
        DirectVoiceOptions.from_settings(cfg)


def test_real_sdk_hybrid_constructor_is_local_and_text_only(forbid_network):
    pytest.importorskip("livekit.plugins.openai")
    pytest.importorskip("livekit.plugins.elevenlabs")
    pytest.importorskip("livekit.plugins.silero")

    async def inspect_session():
        session = build_voice_session(options())
        assert session.llm._opts.modalities == ["text"]
        assert session.llm._opts.turn_detection is None
        assert session.llm.capabilities.audio_output is False
        assert session.stt is None
        assert session.tts._opts.model == "eleven_flash_v2_5"
        assert session.vad is not None
        # Exercise the SDK's actual start-time compatibility gate, which the
        # earlier constructor-only smoke missed (0.20s VAD was rejected).
        from livekit.agents.voice.audio_recognition import AudioRecognition
        AudioRecognition._check_vad_silence_requirement(SimpleNamespace(
            _turn_detector=session.turn_detection, _vad=session.vad))
        assert session.turn_detection._model == "turn-detector-v1-mini"
        assert session.options.interruption["mode"] == "vad"
        assert session.options.interruption["enabled"] is True
        assert session.options.interruption["min_words"] == 0
        assert session.options.interruption["discard_audio_if_uninterruptible"] is False
        await session.aclose()

    asyncio.run(inspect_session())


def test_real_sdk_cascaded_constructor_has_no_inference_gateway(forbid_network):
    pytest.importorskip("livekit.plugins.openai")
    pytest.importorskip("livekit.plugins.elevenlabs")
    pytest.importorskip("livekit.plugins.silero")

    async def inspect_session():
        cfg = replace(options(), mode="cascaded", llm_model="gpt-4.1-mini")
        session = build_voice_session(cfg)
        assert session.stt is not None
        assert session.llm.model == "gpt-4.1-mini"
        assert session.turn_detection._cloud_opts is None
        assert session.options.preemptive_generation["enabled"] is False
        await session.aclose()

    asyncio.run(inspect_session())


def test_native_audio_manifest_and_credentials_are_provider_specific():
    cfg = replace(
        options(),
        mode="native_audio",
        elevenlabs_api_key="",
        tts_model="",
        voice_id="",
        native_voice="cedar",
        native_eagerness="low",
    )
    manifest = voice_pipeline_manifest(cfg)
    assert manifest["native_voice"] == "cedar"
    assert manifest["server_turn_detection"] is True
    assert manifest["local_turn_detector"] is False
    assert manifest["elevenlabs_model"] is None
    assert manifest["brightwater_runtime_compatible"] is False
    assert manifest["usage_boundary"].startswith("lab-only")
    assert "session.say()" in manifest["runtime_incompatibility"]
    assert manifest["tts_aligned_transcript"] is False
    assert cfg.openai_api_key not in json.dumps(manifest)
    assert manifest["qualification"].startswith("unmeasured")
    with pytest.raises(ValueError, match="voice_native_voice"):
        replace(cfg, native_voice="unknown")
    with pytest.raises(ValueError, match="voice_native_eagerness"):
        replace(cfg, native_eagerness="immediate")
    with pytest.raises(ValueError, match="native_audio requires"):
        replace(cfg, llm_model="gpt-4.1-mini")
    with pytest.raises(RuntimeError, match="native_audio is lab-only"):
        build_voice_session(cfg)
    with pytest.raises(ValueError, match="requires native_audio"):
        build_native_audio_lab_session(options())


def test_native_audio_needs_no_elevenlabs_or_silero_constructor(forbid_network, monkeypatch):
    pytest.importorskip("livekit.plugins.openai")
    # Native mode must be viable with no ElevenLabs/Silero plugin installed.
    monkeypatch.setitem(sys.modules, "livekit.plugins.elevenlabs", None)
    monkeypatch.setitem(sys.modules, "livekit.plugins.silero", None)

    async def inspect_session():
        cfg = replace(
            options(), mode="native_audio", elevenlabs_api_key="", tts_model="", voice_id=""
        )
        session = build_native_audio_lab_session(cfg)
        assert session.llm._opts.modalities == ["audio"]
        assert session.llm._opts.voice == "marin"
        assert session.llm.capabilities.audio_output is True
        assert session.llm.capabilities.turn_detection is True
        # Lab-only: native audio cannot fulfill exact session.say() scripts.
        # The Brightwater factory rejects this mode rather than pretending
        # conversation audio also supplies a deterministic script path.
        assert session.llm.capabilities.supports_say is False
        assert session.tts is None
        turn = session.llm._opts.turn_detection
        assert turn.type == "semantic_vad"
        assert turn.eagerness == "low"
        assert turn.interrupt_response is True
        assert turn.create_response is True
        assert session.turn_detection == "realtime_llm"
        assert session.options.interruption["enabled"] is True
        assert session.options.interruption["discard_audio_if_uninterruptible"] is False
        assert session.vad is None
        assert session.stt is None
        await session.aclose()

    asyncio.run(inspect_session())
