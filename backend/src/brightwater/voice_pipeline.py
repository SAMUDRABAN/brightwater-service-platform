"""Direct OpenAI/ElevenLabs session construction for LiveKit Agents 1.8.10.

Constructing this factory does not start a call, download turn-model weights or
make provider inference requests. Session.start() does real work and must only
be reached through the authorised runtime. The local turn model needs its files
prepared with the worker's download-files command before offline deployment.

The default hybrid consumes audio with OpenAI Realtime, requests TEXT output,
and speaks that output with ElevenLabs. OpenAI server turn-taking is disabled:
the pinned local v1-mini detector and Silero own turn boundaries. This is not
LiveKit Inference and needs no LiveKit Cloud inference credentials. A LiveKit
server/SIP route is still independently required for telephone transport.

The native_audio comparator is LAB-ONLY: it uses OpenAI audio output and server
semantic VAD but cannot fulfill Brightwater's deterministic session.say() scripts.
build_voice_session rejects it; the explicitly named lab factory is separate.
No deprecated Speech API TTS workaround is enabled.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class DirectVoiceOptions:
    """Explicit provider configuration; secrets are excluded from repr/manifest."""

    openai_api_key: str = field(repr=False)
    elevenlabs_api_key: str = field(repr=False)
    stt_model: str
    llm_model: str
    tts_model: str
    voice_id: str
    mode: Literal["realtime_text", "cascaded", "native_audio"] = "realtime_text"
    native_voice: Literal["marin", "cedar"] = "marin"
    native_eagerness: Literal["low", "medium", "high", "auto"] = "low"
    endpoint_min_seconds: float = 0.4
    endpoint_max_seconds: float = 3.0
    interruption_min_seconds: float = 0.1
    false_interruption_seconds: float = 2.0
    voice_speed: float = 0.95
    voice_stability: float = 0.5
    voice_similarity: float = 0.75
    voice_speaker_boost: bool = True
    preemptive_generation: bool = False

    def __post_init__(self) -> None:
        # Errors identify the missing setting, never echo its supplied value.
        if self.mode not in {"realtime_text", "cascaded", "native_audio"}:
            raise ValueError("voice_direct_mode must be realtime_text, cascaded or native_audio")
        required = ["openai_api_key", "stt_model", "llm_model"]
        if self.mode != "native_audio":
            required.extend(["elevenlabs_api_key", "tts_model", "voice_id"])
        for name in required:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Direct voice requires {name}")
        if self.mode in {"realtime_text", "native_audio"} and not self.llm_model.startswith(
            "gpt-realtime"
        ):
            raise ValueError(f"{self.mode} requires a direct gpt-realtime model ID")
        if self.mode == "cascaded" and "realtime" in self.llm_model:
            raise ValueError("cascaded requires a text chat model, not a realtime model")
        if any("/" in name for name in (self.stt_model, self.llm_model, self.tts_model)):
            raise ValueError("Use direct provider model IDs, not inference provider/model IDs")
        if not 0 <= self.endpoint_min_seconds <= self.endpoint_max_seconds:
            raise ValueError("Endpoint delay bounds must be nonnegative and ordered")
        if self.endpoint_max_seconds <= 0:
            raise ValueError("Endpoint maximum must be positive")
        if self.interruption_min_seconds <= 0 or self.false_interruption_seconds <= 0:
            raise ValueError("Interruption durations must be positive")
        if self.mode == "native_audio":
            if not 0.25 <= self.voice_speed <= 1.5:
                raise ValueError("OpenAI native voice speed must be between 0.25 and 1.5")
        elif not 0.7 <= self.voice_speed <= 1.2:
            raise ValueError("ElevenLabs voice speed must be between 0.7 and 1.2")
        if not 0 <= self.voice_stability <= 1 or not 0 <= self.voice_similarity <= 1:
            raise ValueError("Voice stability and similarity must be between zero and one")
        if self.native_voice not in {"marin", "cedar"}:
            raise ValueError("voice_native_voice must be marin or cedar")
        if self.native_eagerness not in {"low", "medium", "high", "auto"}:
            raise ValueError("voice_native_eagerness must be low, medium, high or auto")

    @classmethod
    def from_settings(cls, cfg: Any) -> "DirectVoiceOptions":
        def secret(name: str) -> str:
            value = getattr(cfg, name, "")
            return value.get_secret_value() if hasattr(value, "get_secret_value") else value

        return cls(
            openai_api_key=secret("openai_api_key"),
            elevenlabs_api_key=secret("elevenlabs_api_key"),
            stt_model=getattr(cfg, "voice_stt_model", ""),
            llm_model=getattr(cfg, "voice_llm_model", ""),
            tts_model=getattr(cfg, "voice_tts_model", ""),
            voice_id=getattr(cfg, "voice_id", ""),
            mode=getattr(cfg, "voice_direct_mode", "realtime_text"),
            native_voice=getattr(cfg, "voice_native_voice", "marin"),
            native_eagerness=getattr(cfg, "voice_native_eagerness", "low"),
            voice_speed=getattr(cfg, "voice_speed", 0.95),
            voice_stability=getattr(cfg, "voice_stability", 0.5),
            voice_similarity=getattr(cfg, "voice_similarity", 0.75),
            voice_speaker_boost=getattr(cfg, "voice_speaker_boost", True),
            preemptive_generation=getattr(cfg, "voice_preemptive_generation", False),
        )


def voice_pipeline_manifest(cfg: Any) -> dict[str, Any]:
    """Safe configuration evidence. No credentials or claims of qualification."""
    opts = cfg if isinstance(cfg, DirectVoiceOptions) else DirectVoiceOptions.from_settings(cfg)
    if opts.mode == "native_audio":
        return {
            "implementation": "direct-provider-v1",
            "agents_sdk": "1.8.10",
            "mode": opts.mode,
            "openai_model": opts.llm_model,
            "transcription_model": opts.stt_model,
            "audio_output_provider": "openai",
            "native_voice": opts.native_voice,
            "voice_id": opts.native_voice,
            "voice_speed": opts.voice_speed,
            "language": "en; British-English delivery requires agent instructions and audition",
            "turn_detector": "openai-server-semantic-vad",
            "server_turn_detection": True,
            "semantic_eagerness": opts.native_eagerness,
            "create_response": True,
            "interrupt_response": True,
            "session_turn_detection": "realtime_llm",
            "local_turn_detector": False,
            "elevenlabs_model": None,
            "brightwater_runtime_compatible": False,
            "runtime_incompatibility": (
                "OpenAI Realtime supports_say is false and no deterministic TTS is configured; "
                "exact opening, booking readback and safety scripts cannot use session.say()."
            ),
            "usage_boundary": "lab-only; build_voice_session rejects this mode",
            "tts_aligned_transcript": False,
            "preemptive_generation": False,
            "qualification": "unmeasured; native-audio comparator, not a quality claim",
            "limitations": [
                "OpenAI owns semantic endpointing/interruptions; local VAD/adaptive knobs do not apply.",
                "A native voice is not a guaranteed British accent; prompt and actual listening must qualify delivery.",
                "Native transcript timing is not proof of caller hearing or booking consent.",
                "Voice is fixed after audio is emitted; compare candidates in separate sessions.",
                "No supported deterministic say/readback/safety path is configured; not a complete Brightwater phone runtime.",
                "Recording, consent, suppression, safety and confirmation remain runtime/backend responsibilities.",
            ],
        }
    return {
        "implementation": "direct-provider-v1",
        "agents_sdk": "1.8.10",
        "mode": opts.mode,
        "openai_model": opts.llm_model,
        "transcription_model": opts.stt_model,
        "elevenlabs_model": opts.tts_model,
        "voice_id": opts.voice_id,
        "language": "en",
        "turn_detector": "local-v1-mini",
        "server_turn_detection": False,
        "interruption_mode": "vad",
        "interruption_min_words": 0,
        "endpoint_min_seconds": opts.endpoint_min_seconds,
        "endpoint_max_seconds": opts.endpoint_max_seconds,
        "interruption_min_seconds": opts.interruption_min_seconds,
        "false_interruption_seconds": opts.false_interruption_seconds,
        "voice_speed": opts.voice_speed,
        "voice_stability": opts.voice_stability,
        "voice_similarity": opts.voice_similarity,
        "voice_speaker_boost": opts.voice_speaker_boost,
        "tts_encoding": "pcm_24000",
        "tts_aligned_transcript": True,
        "provider_tts_logging": True,
        "preemptive_generation": opts.preemptive_generation and opts.mode == "cascaded",
        "preemptive_tts": False,
        "qualification": "unmeasured; requires actual PSTN listening and action tests",
        "limitations": [
            "No cloud adaptive interruption classification is enabled; brief backchannels may interrupt.",
            "Local semantic end-of-turn inference requires prepared model files and worker inference process.",
            "Aligned TTS transcripts are not proof that a caller heard audio or consented to a booking.",
            "British accent comes from the selected licensed voice, not the language code alone.",
            "Realtime hybrid still incurs external TTS/network latency and is not full-duplex audio generation.",
            "Recording, consent, suppression, safety and confirmation gates remain runtime/backend responsibilities.",
        ],
    }


def build_voice_session(cfg: Any) -> Any:
    """Build an unstarted AgentSession; call from the worker's async runtime.

    Required voice extras, pinned to 1.8.10: livekit-agents,
    livekit-plugins-openai, livekit-plugins-elevenlabs, livekit-plugins-silero.
    v1-mini is built into Agents: the legacy turn-detector plugin is not needed.
    No credential-file loading, environment mutation or network warm-up occurs.
    """
    opts = cfg if isinstance(cfg, DirectVoiceOptions) else DirectVoiceOptions.from_settings(cfg)
    if opts.mode == "native_audio":
        raise RuntimeError(
            "native_audio is lab-only: no supported deterministic session.say/readback/safety path; "
            "use realtime_text or cascaded for the Brightwater runtime"
        )
    try:
        from livekit.agents import AgentSession, TurnHandlingOptions, inference
        from livekit.plugins import elevenlabs, openai, silero
        from openai.types import realtime
    except ImportError:
        raise RuntimeError(
            "Install the pinned direct voice extras: livekit-agents==1.8.10, "
            "livekit-plugins-openai==1.8.10, livekit-plugins-elevenlabs==1.8.10, "
            "livekit-plugins-silero==1.8.10"
        ) from None

    vad = silero.VAD.load(
        min_speech_duration=0.05,
        min_silence_duration=0.25,
        prefix_padding_duration=0.5,
        activation_threshold=0.5,
        sample_rate=16000,
        force_cpu=True,
    )
    # Pin the mini version. Auto-selection may choose billable cloud v1 in dev.
    detector = inference.TurnDetector(version="v1-mini")
    tts = elevenlabs.TTS(
        api_key=opts.elevenlabs_api_key,
        base_url="https://api.elevenlabs.io/v1",
        voice_id=opts.voice_id,
        model=opts.tts_model,
        voice_settings=elevenlabs.VoiceSettings(
            stability=opts.voice_stability,
            similarity_boost=opts.voice_similarity,
            speed=opts.voice_speed,
            use_speaker_boost=opts.voice_speaker_boost,
        ),
        encoding="pcm_24000",
        language="en",
        auto_mode=True,
        sync_alignment=True,
        enable_logging=True,
        enable_ssml_parsing=False,
    )
    if opts.mode == "realtime_text":
        llm = openai.realtime.RealtimeModel(
            api_key=opts.openai_api_key,
            base_url="https://api.openai.com/v1",
            model=opts.llm_model,
            modalities=["text"],
            turn_detection=None,
            input_audio_transcription=realtime.AudioTranscription(
                model=opts.stt_model,
                language="en",
            ),
            input_audio_noise_reduction=None,
            tracing=None,
        )
        stt = None  # Realtime model transcribes; do not duplicate paid STT.
    else:
        stt = openai.STT(
            api_key=opts.openai_api_key,
            base_url="https://api.openai.com/v1",
            model=opts.stt_model,
            language="en",
            detect_language=False,
            use_realtime=True,
            vad=vad,
        )
        llm = openai.LLM(
            api_key=opts.openai_api_key,
            base_url="https://api.openai.com/v1",
            model=opts.llm_model,
            parallel_tool_calls=False,
            store=False,
        )
    return AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        turn_handling=TurnHandlingOptions(
            turn_detection=detector,
            endpointing={
                "mode": "fixed",
                "min_delay": opts.endpoint_min_seconds,
                "max_delay": opts.endpoint_max_seconds,
            },
            interruption={
                "enabled": True,
                "mode": "vad",
                "min_duration": opts.interruption_min_seconds,
                "min_words": 0,
                "resume_false_interruption": True,
                "false_interruption_timeout": opts.false_interruption_seconds,
                "discard_audio_if_uninterruptible": False,
            },
            preemptive_generation={
                "enabled": opts.preemptive_generation and opts.mode == "cascaded",
                "preemptive_tts": False,
                "max_retries": 1,
                "max_speech_duration": 6.0,
            },
        ),
        max_tool_steps=5,
        use_tts_aligned_transcript=True,
        user_away_timeout=None,  # Explicit hold/silence policy belongs to controller.
        expressive=False,
    )


def build_native_audio_lab_session(cfg: Any) -> Any:
    """Unstarted pure-audio benchmark session; NOT a Brightwater runtime factory.

    OpenAI Realtime cannot say arbitrary exact text via the installed SDK. No TTS
    is configured, so do not use this for opening/readback/safety phone workflows.
    The standard build_voice_session path intentionally rejects native_audio.
    Server turn detection must stay paired with realtime_llm and enabled
    interruptions. Framework VAD duration/word/adaptive options are deliberately
    omitted because they do not control server-side realtime turn decisions.
    """
    opts = cfg if isinstance(cfg, DirectVoiceOptions) else DirectVoiceOptions.from_settings(cfg)
    if opts.mode != "native_audio":
        raise ValueError("The lab native-audio factory requires native_audio mode")
    try:
        from livekit.agents import AgentSession, TurnHandlingOptions
        from livekit.plugins import openai
        from openai.types import realtime
    except ImportError:
        raise RuntimeError(
            "Install native voice extras: livekit-agents==1.8.10 and livekit-plugins-openai==1.8.10"
        ) from None
    model = openai.realtime.RealtimeModel(
        api_key=opts.openai_api_key,
        base_url="https://api.openai.com/v1",
        model=opts.llm_model,
        voice=opts.native_voice,
        modalities=["audio"],
        speed=opts.voice_speed,
        input_audio_transcription=realtime.AudioTranscription(
            model=opts.stt_model,
            language="en",
        ),
        turn_detection=realtime.realtime_audio_input_turn_detection.SemanticVad(
            type="semantic_vad",
            eagerness=opts.native_eagerness,
            create_response=True,
            interrupt_response=True,
        ),
        input_audio_noise_reduction=None,
        tracing=None,
    )
    return AgentSession(
        llm=model,
        stt=None,
        tts=None,
        vad=None,
        turn_handling=TurnHandlingOptions(
            turn_detection="realtime_llm",
            interruption={"enabled": True, "discard_audio_if_uninterruptible": False},
            preemptive_generation={"enabled": False},
        ),
        max_tool_steps=5,
        use_tts_aligned_transcript=False,
        user_away_timeout=None,
        expressive=False,
    )
