# Playback acknowledgement sequence repair

9 November 2026. Status: DONE_WITH_CONCERNS. A receiver defect is reproduced and repaired; attribution to the last carrier failure and fresh handset qualification remain open.

## Symptom and retained phone evidence

Calls 16 and 17 were disconnected by the service after playback_checkpoint_timeout, before a new CP12 booking. Call 17 verified identity and successfully queried fixture availability. Its pre-cleanup diagnostic retained 50 sent pending checkpoints, none final, 7954 outstanding samples and 287 earlier acknowledgements. It did not retain the rejected input event sequence numbers. Those facts establish stalled acknowledgement progress, but do not establish which event was discarded or whether the carrier itself stopped sending receipts. No previous call is reclassified as successful.

## Reproduced root cause

The receiver applied one global sequence-number watermark to caller audio and playback control events. A named playedStream receipt arriving with a number below the latest caller-media event was silently dropped before its stream or checkpoint was checked. The audio remained outstanding and the watchdog closed the stream. A duplicate start/media filter was therefore also acting as a playback-receipt filter.

A deterministic regression first delivers newer caller audio, then a receipt for the exact final checkpoint actually sent. Eight delayed sequence values all fail on the previous code by returning interrupted playback after a timeout. A ninth negative test shows the old short circuit also ignored a wrong-stream receipt before validating its binding. All nine fail before the change and pass after it.

## Change and safety fact

playedStream receipts are validated and dispatched independently of the caller-media watermark. The sequence field must still be a nonnegative integer. The receipt must belong to the bound authenticated stream, match a pending randomly named checkpoint, and refer to one already sent. Matching checkpoints are removed exactly once. A receipt cannot rewind or advance caller-audio replay protection. Cleared-generation and duplicate receipts remain ineffective; final playback still requires a real matching receipt. Timeouts and queue bounds are unchanged.

The safety fact is that a receipt proves only a pending, sent checkpoint on this stream. The repair does not infer playback from elapsed time, provider captions or queued audio, and cannot bypass identity or booking guards. Existing SDK speaking/clear/interruption tests and new wrong-stream/duplicate tests exercise these boundaries. This is executable local/integration evidence, not a fresh carrier observation.

Plivo's protocol describes checkpoints and named playedStream receipts. Its official Python Stream SDK dispatches playedStream by event type without a cross-media sequence filter. These sources support independent receipt processing; they do not prove that call 17 contained a delayed sequence.

- [Plivo protocol reference](https://www.plivo.com/docs/voice-agents/audio-streaming/concepts/audio-streaming-reference)
- [Official Python streaming handler](https://github.com/plivo/plivo-stream-sdk-python/blob/main/plivo_stream/base.py)

## Verification and remaining limits

The transport suite passes 30 tests after the change, including actual pinned LiveKit SDK speaking/interruption integration. The nine new cases fail against the preceding implementation. Ruff and whitespace checks pass. Full-suite and deployment results follow below.

Calling remains paused at 17/17 used. No eighteenth call is authorised. Prior boiler booking and failed call recordings remain intact. No new main-diary write or external phone call was made during this repair. UK campaign controls remain disabled; native SIP remains disabled/unassigned. Broader voice latency, initial speech-onset association and UK production qualification are separate outstanding work.

Exact runtime `327486d7b5d538e0b28cc81cde819f6aca0496ff` passed364 native tests in159.66 seconds and364 Linux/PostgreSQL17 tests in158.21 seconds. It is deployed healthy with call admission paused. The owner subsequently explicitly authorised one eighteenth attended verification call, capped at180 seconds; its result will be recorded separately.

## Eighteenth attended verification

The owner explicitly approved one further three-minute call. It verified identity, queried the diary, delivered the full fictional CP12 arrangement and received “Yes, please do it.” Exactly one confirmed engineering booking was saved for £75 including VAT. The provider transcript read Tuesday17 November2026, morning8am–noon. The booking ID is retained privately with the call evidence; this is a fictional assessment appointment, not a real customer reservation. The prior boiler booking remains intact.

The call finished with outcome Booked. ElevenLabs termination reason was “end_call tool was called.” Plivo reports108 seconds, Normal Hangup/API Request, and its signed-ended event finalised the record. The managed diagnostic reports no transport failure. The protected stereo recording is106.7865 seconds/1928340 bytes; anonymous access401 and authorised access200 were verified. No replay or automatic redial occurred.

This is one successful post-repair handset flow through booking and closing. It does not prove the precise sequence ordering of the previous failure, nor qualify every carrier/interruption scenario or production latency. Initial identity recovery and broader latency work remain open. User audio-quality feedback is separate from these system observations.

Call admission was paused again and the gateway is healthy. All18 attempts are used; no nineteenth call is authorised. API3ae77c71916b0dd802b3f2214dd8c2f5f712114f carries only the explicitly approved18-call ceiling after the tested repair. Gateway327486d7b5d538e0b28cc81cde819f6aca0496ff remains the tested repair. Source, logs and earlier failed outcomes remain preserved.
