# Voice baseline and evidence boundary

The implementation now has two explicit provider paths. Both are candidates, and neither has passed a handset study.

## Direct provider path

OpenAI Realtime text + ElevenLabs TTS (or cascaded OpenAI STT/LLM + ElevenLabs TTS), with pinned LiveKit Agents/OpenAI/ElevenLabs/Silero plugins 1.8.10. It uses local `v1-mini` semantic turn detection and CPU Silero, without LiveKit Cloud inference credentials. A worker prewarm hook initializes the local EOT/VAD singletons before admitting jobs. Provider sessions, transport and complete audible behavior still need testing.

Settings are explicit in `backend/src/brightwater/voice_pipeline.py`: 0.4-second minimum/3-second maximum endpoint delay, 0.1-second VAD interruption minimum, zero minimum words, false-interruption resume, preserved buffered audio and no speculative generation. ElevenLabs PCM24k/aligned transcript is used at a provisional speed of 0.95. These are starting settings, not achieved timing results. There is no hosted adaptive backchannel classifier in this direct configuration, so short acknowledgements can still cause false stops and must be measured.

The original LiveKit Inference path retains cloud `v1` semantic detection/adaptive interruption and its separate account requirements. Do not pass self-hosted LiveKit transport keys off as cloud inference credentials.

## Observed provider checks, 6 November 2026

All four supplied account credentials authenticated through read-only APIs. OpenAI Realtime `gpt-realtime-2.1` also completed a bounded text connectivity request with the expected reply. Four British ElevenLabs `eleven_flash_v2_5` audition clips were actually synthesized (233 characters each); OpenAI `gpt-4o-mini-transcribe` recovered the selected Tuesday/Thursday/diary phrases in all four. These clips and results are in the separate voice-audition output. They are clean-script diagnostics, not a naturalness score, a blinded study, latency distribution or PSTN evidence.

## Evidence and safety boundaries

Caller/assistant transcript events, interruption flags and server-side state changes are captured. Server timestamps do not measure handset audible onset or stop. Deterministic booking read-back still waits for playout; a later correction invalidates the older affirmative. The public SDK session report supplies completed Ogg audio to the authenticated recording upload; encrypted storage/auth/playback tests passed using explicitly synthetic storage fixtures, not real call recordings.

No supplied API key is in source. The recording encryption key is independent from provider keys. An invalid settings error is configured not to echo raw secret inputs. Recording access requires operator credentials; uploads require a different trusted runtime credential.

Official references: [OpenAI Realtime](https://developers.openai.com/api/docs/guides/realtime), [ElevenLabs speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [LiveKit turn handling](https://docs.livekit.io/agents/logic/turns/). Provider documentation informed configuration; observed checks above have deliberately narrower claims.

Remaining qualification includes real UK calling, independent safety/opt-out handling, difficult accents/digits/noise, correction/identity behavior, phone timing, audible recording capture, cloud failure/drain/restore and independent human evaluation. All telephone voice and interaction scores remain NOT EVALUATED.
