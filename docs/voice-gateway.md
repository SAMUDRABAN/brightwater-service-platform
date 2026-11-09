# Direct Plivo voice service

6 November 2026. This is a deployed engineering candidate for Brightwater's UK service workflow. Customer campaigns remain disabled. Clear handset speech has been confirmed by the owner. On call 10 the owner reported a much better flow, but booking failure and long pauses remain quality issues. Conversation and task qualification remain incomplete.

## Deployment and scope

The London office/business API, PostgreSQL, Redis, Celery and fenced Beat use the approved $24/month host. The separate India voice gateway, Redis and TLS proxy use the additionally approved $12/month Bangalore host. Total incremental compute is $36/month before tax and provider usage. The unrelated existing Bangalore server was not changed. Different server roles do not establish high availability or a mirror.

Office: https://office.46.101.11.137.sslip.io . Voice: https://voice.159.65.149.114.sslip.io . The voice release is `f82759f92c71bcb6e04c384ddba0e19b3c61cfba`; the API release is `f8dcf246026df82d54d3b0fbdf09dc1be68129cd`. Office and maintenance workers retain the unchanged `f98f9671cb6507fee2a28fe919bcaeb827d437e4` release. The API has its own `api-current` deployment pointer; the older full-stack `current` pointer must not be used to rebuild the newer API.

Only one privately allowlisted, explicitly consented Indian recipient is admitted for attended engineering roleplay. Each call is limited to 180 seconds. Every additional attempt requires fresh readiness and its bounded allowance; ten attempts have been authorised individually. No automatic redial occurs after a busy line, failure or uncertain initiation. Normal UK campaigns and their database switch remain off; +44 validation is unchanged. No assessment sample number was dialled. Engineering property/diary details are labelled fictional and excluded from customer campaign metrics.

## Voice pipeline

LiveKit Agents 1.8.10 runs roomless with custom Plivo audio input/output, OpenAI streaming transcription (`gpt-4o-mini-transcribe`), conversation/tools (`gpt-4.1-mini`) and ElevenLabs Flash v2.5 with the provisional British Alice voice. Local Silero VAD and local semantic endpointing control turns. No LiveKit Cloud or SIP account is required for this direct path. Hosted adaptive interruption classification is not claimed.

The runtime uses `livekit.agents.utils.http_context.open()` and warms native models before readiness. Silero silence is at least 250 ms as required by the actual SDK. Python is pinned to 3.12 because the current G.711 adapter uses deprecated audioop. Realtime-text/native-audio alternatives remain unqualified for this deterministic readback path.

Audio is native 8 kHz mu-law. Plivo starts sequence numbering at zero and can send an internal account label rather than the public Auth ID. Ownership is verified through the authenticated Plivo stream-metadata API, matching the signed-answer-bound CallUUID and StreamUUID. Bounded recent pre-roll is retained before the first input consumer attaches; after attachment, input overflow fails closed. Output is paced with checkpoints. Clear/interruption invalidates old generations, and completed SDK speech waits for the matching provider playout acknowledgement. A provider acknowledgement is not proof of human hearing or understanding.

## Authentication and recording

HTTP answer/status/recording callbacks require genuine Plivo V3 signatures against the configured public HTTPS origin. Answer verifies the configured destination and caller ID. RequestUUID and actual CallUUID are distinct.

Engineering media authentication explicitly selects `answer_bound_token`: a capability delivered only by the verified answer, binding internal call and actual CallUUID, expiring after 120 seconds and claimed once atomically. Verified-answer state and authenticated stream ownership are required. Missing, expired, forged, cross-call and replayed credentials are denied. The actual carrier WebSocket V3 signature has not qualified; its result remains separate diagnostic evidence. The strict V3-plus-token mode remains available and is not falsely reported as passing.

Answer XML starts background stereo WAV session recording before Stream. A separate signed initial action with RecordingDuration=-1 binds one RecordingID to the verified call. The greeting waits at most ten seconds for confirmed recording start. The matching final-ready callback queues delivery once. This replaced an incorrect assumption that the REST Record response immediately supplies an ID: actual India responses were HTTP 200, “async api spawned”. The sixth call's short recording existed despite that missing immediate ID.

The durable worker verifies recording metadata through the authenticated carrier API, permits only bounded HTTPS downloads from approved provider storage, converts to Ogg and uploads to encrypted office storage. Callback-supplied URLs are not trusted. Processing jobs survive restarts; failures remain reviewable. Operator playback requires authentication. Actual short-call recovery and the seventh call's full 178.88-second stereo recording passed protected playback; unauthenticated playback returned 401. Provider storage authentication/retention and wider recovery policy still need production qualification.

## Conversation repairs

The recipient name and current UK date are supplied explicitly before SDK session start. The agent has an explicit outbound renewal objective: after successful identity, return the verified account within the same confirmation tool, explain its unresolved service obligation, and offer arrangement. Account retrieval still occurs only after backend identity assertion succeeds. It no longer relies on an implied inbound/outbound role.

Direct natural self-introductions are supported. A fresh colloquial affirmative such as “Yeah, yeah, you are” or “Uh, yes, you are” is accepted only after the actual named question completed playback. The backend requires matching name/text, delivered notice, original verified speech timing, latest caller evidence and bounded freshness. Interruptions, handoffs, intervening questions and new incomplete questions invalidate older consent. Question tools are serialized and deduplicated per caller turn; failed clarification is bounded.

There is no live human transfer. Prompts and tool results permit recording a callback request after caller agreement, and describe that acknowledgement honestly. They do not claim a live connection, notification, immediate availability or a response time. A callback without captured caller evidence is not recorded.

Booking still requires the current proposal, completed readback and fresh explicit confirmation; corrections invalidate earlier evidence. Runtime timing checks fail closed. The booking backend now independently requires the speech_timing_verified boolean as well as its existing readback/fingerprint/time-order checks. Natural booking assent such as “Yeah, please do it” and “Yeah, yeah, do it” is supported within those guards. A rejected consent returns confirmation-required rather than a misleading slot failure. finish_call waits for its current spoken preface through SDK RunContext.wait_for_playout before ending the connection. No successful handset booking is claimed.

## Retained handset evidence

Calls 1–6 failed before successful agent speech. Captured real packets established the zero-based start, account-label namespace and pre-consumer queue defects; fixes were reproduced against the exact packet and startup traffic. Call 6 also exposed asynchronous recording acknowledgement.

Call 7 produced 12 agent utterances and 14 caller turns. The owner confirmed clear speech, while flagging conversation quality. Plivo enforced Scheduled Hangup at 180 seconds; the stereo recording is 178.88 seconds. Identity did not complete and no booking occurred.

Call 8 exposed rejection of natural colloquial replies and an unsupported live-transfer offer. Those exact reply strings now pass backend regressions, and callback capabilities were corrected. Call 9 was unanswered: carrier Busy Line after 22 seconds, zero answered duration, no agent session. Call 10 completed identity confirmation, explained the actual fixture service obligation, offered availability and completed a proposal readback. Its natural booking assent was rejected by the older parser, so no booking was created; a caller callback request was recorded. The repaired booking parser and closing-playout change still need a fresh handset test. The recording is protected in the office call view.

The first eight answered records were reconciled through authenticated carrier CDRs, with CallUUID/from/to/answer/end verification. Their prior No answer classification remains in audit events; the current outcome is unknown, with internal review rather than invented business success. Genuine unanswered calls still retain No answer. All records remain available.

## Verification and remaining gates

Current substantive code: native backend **202 passed in 21.97s**, isolated Linux/PostgreSQL 17 **202 passed in 53.03s**, Ruff clean. Subsequent call-ceiling-only changes were checked separately, including rejection above the authorised ceiling. Frontend source is unchanged from its previously passing eight authentication tests and production build.

Four narrow current-prompt actual-model checks passed: confirmed identity leads to account lookup and an outbound service explanation; unclear identity offers a callback; recorded callback is acknowledged without invented transfer; unavailable live transfer is declined. These use synthetic text/isolated assessment fixtures and actual SDK tool schemas, with no phone calls or business writes. An earlier inbound-style failure is retained alongside the improved prompt result. They are not conversation-quality certification.

No independent voice ratings, handset latency distribution, interruption-stop percentile, UK carrier qualification, complete assessment-call matrix or human-indistinguishability result is claimed. Authoritative business diary/customer integration, enterprise identity/roles, retention/deletion, external monitoring, backup/recovery and failover qualification remain release gates. See release-readiness.md.

## Latency follow-up

Owner feedback on call 10 was much better flow, but still slow with pauses. One avoidable model/tool roundtrip was removed: successful identity now includes the scoped verified account. The actual-model post-confirmation fixture needed one request rather than the earlier two. This is a measured request-count reduction, not a measured handset latency improvement.

Optional EOU, transcription, model TTFT/duration and TTS TTFB/duration metrics are filtered to numeric timing fields and stored locally in Redis at voice:latency:<session>. Each list is bounded to 256 entries with a 24-hour TTL. No transcript, audio or credentials are stored there. Telemetry failures do not terminate calls or block business-event capture. The deployed storage path was checked with a temporary synthetic sample and cleaned up.

Endpointing thresholds were not shortened without evidence. The booking-consent repair, closing-playout ordering and latest latency change still require a fresh attended call; no eleventh call is authorised.


## Lily and conversation update — 7 November

Current India release: `0325039d76cacdb82ac514c3cfe4eada62cc0706`. Selected profile is Lily (`pFZP5JQG7iQjIQuC4Bku`), `eleven_v4_turbo`, speed1.0/stability0.5/similarity0.75. Cascaded GPT-4.1 mini plus timestamp-bearing mini transcription remains active. Early LLM generation is bounded and cannot execute tools before final authorisation; speculative TTS is disabled. The Plivo bridge now emits SDK `playback_started` once per segment only after provider checkpoint evidence. A deployed no-phone check produced35,200mu-lawbytes and observed SDK speaking. Actual new handset delivery/interruptions/booking/latency still need qualification. The new realtime semantic lab replay passed isolated identity/timing but is not the active mode. See conversation-improvement.md.
