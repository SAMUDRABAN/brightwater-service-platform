# Native ElevenLabs candidate

7 November 2026. Engineering evaluation, not customer production qualification.

The user authorised moving the voice conversation to a managed platform while retaining Brightwater's authoritative booking backend. A private ElevenLabs Agents candidate uses Lily, `eleven_v4_turbo`, Scribe Realtime and GPT-4.1. ElevenLabs handles recognition, generation, speech and turn detection. There is no replacement custom STT/TTS loop in this candidate. The existing Plivo carrier stream now connects to the managed backend through the adapter described below.

## Integration and evidence

The office's administrator-only `/managed` page creates a signed provider session. Provider API keys stay server-side. Each session has an expiring capability bound to one evaluation call and, at its first tool request, one provider conversation. A separate workspace secret authenticates provider tool requests; this is not an office operator/runtime token. Secret session variables are bound to tool headers and excluded from model context.

Six native server tools cover identity/account, real availability, proposal preparation, booking confirmation, follow-up creation and finish. Tool bodies bind `system__conversation_history` and `system__is_text_only` directly through provider configuration, rather than accepting an LLM's statement that somebody confirmed. A Redis lease bounds concurrency, expiring capabilities bind sessions, a per-session lock serialises tools, and persisted operation results deduplicate retries.

Provider history is checked as structured role/message data. Account information remains unavailable until the named caller's latest reply passes deterministic identity checks. Proposals require real capacity, eligible gas engineers, valid property ownership, appropriate prices and tenant contacts. A text confirmation requires the full current substantive readback followed by a fresh whole-utterance affirmative. Formatting differences are permitted; wrong address, postcode, service, date/year, window or price are rejected. Existing telephone `speech_timing_verified` guards remain unchanged. No managed text evidence is labelled verified original speech timing.

The general conversation-history REST API returned an empty transcript during the initial active probe. Native system-variable history is therefore used for live business tools. The initial local client-tool relay was an investigation experiment and was not retained as the deployed architecture.

## Isolation

`brightwater_managed_evaluation` is a separate PostgreSQL database with its own restricted login. Initialisation seeds only labelled assessment fixtures and diary blocks. It copies no office/customer records, staff accounts, recordings or real destinations. No telephone dispatch outbox is created. Non-dialable destination labels are used. Reservations and follow-ups persist in this database and are shown as evaluation outcomes in the office; they do not consume the office diary or engineering phone allowance.

Calls are bounded to 180 seconds, one concurrent session and ten provider conversations per day. No phone number is assigned to the candidate. Provider audio/transcript retention is seven days for these fictional engineering tests. The app must not be opened to customers before the remaining privacy, retention and voice gates are qualified.

## Findings retained

- First managed text integration: actual provider/model, real backend and database; identity and availability passed, commit failed because the model spoke a date differently from an overly literal comparison. Failed evaluation retained.
- Revised local end-to-end text integration: actual provider/model completed identity, availability, readback and a single £95 reservation. `Booked` was derived from the stored reservation, not the model's summary. This is integration evidence, not an acoustic rating.
- First synthetic audio smoke: actual managed PCM output was non-silent; ASR missed the beginning of the synthetic caller input, so identity failed. Failure retained. Not a listening, interruption or latency pass.

## Remaining release gates

Voice-mode booking commits deliberately fail closed. Native ordered history does not by itself establish original caller speech onset after completed handset playback. This contract must be demonstrated for the selected managed voice/telephone route before customer booking commits are enabled. Text mode exercises the real reservation code without fabricating audio evidence.

Plivo India to the selected managed SIP region has not been qualified. ElevenLabs supports SIP trunking, but account/region eligibility, caller ID, actual route and handset audio must be verified. No provider switch, replacement number, subscription purchase or further phone call is implied by this candidate. UK campaign calling remains disabled. Independent voice/conversation ratings, real office integration and the other enterprise gates in release-readiness remain open.

## Provider references checked

- https://elevenlabs.io/docs/eleven-agents/customization/personalization/dynamic-variables
- https://elevenlabs.io/docs/eleven-agents/phone-numbers/sip-trunking
- https://api.elevenlabs.io/openapi.json

The current system-variable documentation describes `system__conversation_history` as JSON role/message/tool entries and states that `secret__` variables can be used in tool headers without being passed to the LLM. Provider documentation and API configuration acceptance establish supported interfaces, not measured quality.

## Reproducible setup

Provision the dedicated `brightwater_managed_evaluation` database and a login that owns only that database, using a private password. Set the five `BW_MANAGED_*` fields from `.env.example`; the normal office database URL must continue to identify the office database. `managed_api_key` belongs only in the API's environment. Worker/Beat/web services do not receive the managed provider key or webhook secret.

Initialise without dropping or resetting anything:

```sh
PYTHONPATH=backend/src python scripts/init-managed-evaluation.py
```

Create/update the private provider candidate using privately supplied `ELEVENLABS_API_KEY` and `BRIGHTWATER_MANAGED_WEBHOOK_SECRET`:

```sh
PYTHONPATH=backend/src python scripts/provision-managed-agent.py \
  --state /private/path/eleven-managed-state.json \
  --api-url https://your-api-host
```

Keep that state and the webhook secret together in private deployment configuration; reruns reuse the same candidate, knowledge document and dedicated provider secret. The script refuses to update an agent whose name does not identify the owned Brightwater candidate. No phone-number endpoint is called. Authenticate to the office as an administrator and open `/managed`. Voice requests microphone access only when the administrator presses its button. Ending a session closes the provider socket and finalises the isolated evaluation record; the cap/lease also expires after five minutes. The provider itself limits conversations to three minutes.

## Deployed native evidence

The first native server-tool session on London saved a single real evaluation booking and a `Booked` outcome. An automated caller then kept replying after the backend finish tool; the provider session was still open and subsequently described a completed booking as a failure. This failed closing sequence is retained. The correction adds the provider's native `end_call` tool and a terminal backend result: a repeated request in the same bound completed session returns the saved outcome rather than turning an existing reservation into a reported failure.

A second, native audio smoke continuously streamed silence during startup and then a synthetic caller sentence. Actual ASR recovered “Yes, this is Daniel Reeves.” The backend verified identity and returned the correct boiler-service account. Non-silent Lily PCM output was received; in this single synthetic identity turn the first reply audio arrived 1.913 seconds after the synthetic input ended. This is a harness timestamp, not handset latency, a percentile, a human rating or a full conversation score. The earlier clipped-input audio failure remains part of the evidence.

## Final candidate check

The native Sanjay evaluation saved one £95 afternoon booking, derived `Booked` from the database and emitted a successful native `end_call` tool response. The WebSocket harness closed on that event, matching the official client lifecycle; close code was 1000. The earlier Joan evaluation booked successfully but its ending timed out: the provider had silently ignored a separate `built_in_tools` definition while legacy inline tools were supplied. `end_call` is now registered in the actual tool list and provider readback asserts its presence. This is a verified integration quirk, not a passed earlier ending test.

The browser uses official `@elevenlabs/client` 1.35.0 for microphone capture, playback, interruptions, messages and the end-call lifecycle. No custom browser PCM framing or playback queue remains. The SDK was imported in Node before browser startup and the production Next build passes. Authenticated microphone interaction in the deployed browser still needs administrator use; no credentials were entered into browser automation.

The Amira text harness repeatedly requested a morning when the two returned offers were afternoons; it correctly produced no booking. That scripted harness is not a successful conversation-quality evaluation. Preference-aware searches beyond the first two diary offers and the broader scenario matrix remain release work. The successful final candidate still used a generic further-help question before ending; closing wording remains a conversation polish issue, not a reason to mark its saved booking unsuccessful.

Current server runtime evidence: 262 backend tests pass natively and on isolated Linux/PostgreSQL17. The final provider-registration assertions pass the 26 managed tests; four frontend session tests and the official-client production build pass. All acoustic/conversation ratings remain unmeasured. The carrier and number remain unchanged. The native Plivo adapter supersedes the old conversation pipeline in the India gateway, with admission paused; no twelfth attended telephone call was authorised or placed.

## Conversation repairs and existing Plivo number

The latest owner browser conversation passed identity and reached a booking proposal, but a deliberately unqualified browser-audio commit returned `managed_audio_unqualified`. The model misrepresented this technical restriction as an unclear reply and asked for agreement three times. The spoken readback also omitted the postcode. These are retained failures, not successful bookings.

The tool now distinguishes an unavailable action from ambiguous consent. It acknowledges a clear agreement without claiming a reservation was saved or asking for another yes. A pending carrier-evidence race permits one retry of the same tool without a new caller answer. The prompt requires the postcode, removes spoken tone tags and ends cleanly after a saved booking. Exact owner replies including repeated “yeah” and “yes, book it” pass the narrow affirmative parser; negative, corrected, proxy and quoted replies still fail. Spoken date/address/price normalization allows equivalent number words while rejecting wrong details.

A dedicated signed phone agent shares Lily/v4 Turbo, Scribe Realtime, GPT-4.1 and the authoritative native tools. The existing Plivo number's ownership was checked through authenticated read-only carrier API access. Its application was not changed and no phone number was purchased/imported. After the gateway's existing authenticated answer, stream ownership and recording-start checks, it requests a bound phone capability from the London API and bridges carrier audio to ElevenLabs. Six native business tools remain authoritative; ElevenLabs owns recognition, turns, generation, voice and interruption decisions. Local Silero only observes original speech onset for evidence.

Native provider audio is PCM16k; the existing Plivo edge remains 8k mu-law. High quality RTC resamplers bridge the formats. Two failed non-phone experiments were retained: G711 provider alignment omitted the opening text, and estimated caption durations did not match packet durations. The corrected adapter requires complete declared text coverage including terminal punctuation, then the actual final carrier checkpoint acknowledgement. Queuing audio or receiving a transcript is never proof of completed playback. Interruptions clear pending output; a late ACK cannot validate an interrupted readback.

Original packet reception timestamps are preserved across queues. Server-observed, fresh speech and completed noninterrupted readback are required before existing main-diary identity/booking policy can accept a phone action. A tool/evidence race waits in short read transactions rather than blocking the writer or changing timestamps. Plivo's request identifier stays in the call record; the ElevenLabs conversation identifier is stored separately. Only a server-issued engineering capability can select the main database. Ordinary browser/text evaluations remain isolated.

Actual GPT-4.1 checks passed three recovery/closing cases with synthetic context and no business writes. A live ElevenLabs audio harness recovered a complete named caller reply and correct due service with paced simulated Plivo ACKs. This was not a phone call. Its synthetic caller began 11 ms before the final observed question ACK, so strict main-phone identity would correctly reject that overlap; it is not proof of main-phone identity or booking success. The isolated database suite separately verifies positive ordering and the overlapping-speech rejection.

The current release passes 293 native and 293 isolated Linux/PostgreSQL17 tests, including 31 managed-phone tests. The office client is unchanged from the prior official-SDK build. Actual handset playback, booking, interruption handling, latency percentiles and independent listening scores remain unqualified. Gateway admission is paused, UK campaigns are disabled and the physical allowance remains eleven used of eleven. Non-phone evaluation requests are bounded separately to twenty; each dedicated provider agent retains ten conversations per day, concurrency one and a three-minute maximum. End any browser session before an attended phone test; the shared managed-session lease must be free. No new infrastructure, subscription or staff password reset was performed.

## Contextual booking intent and twelfth call — 8 November 2026

The twelfth attended Plivo call verified identity, offered the correct service and read the complete booking details, but saved no booking. The caller's first agreement began 1.684 seconds after completed noninterrupted carrier playback, with verified original speech timing. The matcher incorrectly added adjacent spoken digits: “PO four zero J T” became PO4JT, losing the zero. It also turned “twenty twenty-six” into 46. The resulting readback rejection caused a loop. The owner confirmed hanging up because it kept repeating details; the gateway's preserved AudioTransportError at disconnect is not proof that the service independently dropped this call. Its protected recording is available; all failure events remain retained.

The readback normalizer now preserves spoken digit sequences and year pairs. Exact call readback tests accept the correct postcode/year and reject wrong postcode/year/price/window. A context-aware server classifier now interprets the latest native customer reply, previous question and prepared appointment. It returns confirm, change, decline, cancel, question or unclear using GPT-4.1-mini structured output. This is semantic inference, not a fixed vocabulary of affirmative phrases and not an agent-supplied confirmation boolean. A yes to a different question, conditional agreement, altered details, quotation, third-party assent, uncertainty or prompt injection cannot independently authorise a booking.

Inference runs before SQL/control locks and has a four-second timeout with no retry. Its result is bound to the call, proposal fingerprint, full latest reply and prior question. Main phone booking still independently verifies original speech, current turn, complete noninterrupted carrier playback, identity, proposal expiry, eligible engineers, capacity and idempotency. A newer reply or changed proposal invalidates the semantic evidence. Model/key/network failure saves nothing and must not trigger repeated requests for another yes. Unchanged cascaded workers retain their existing policy; this integration serves the selected ElevenLabs path.

The new cancel_arrangement native tool cancels the current conversation's pending proposal or saved appointment only after a fresh, contextually clear request. It releases the saved appointment's diary capacity exactly once and cannot revive a cancelled proposal through a booking retry. Historical/other appointments must be identified by the office; the agent cannot guess which to cancel. The final closed result checks confirmed booking state, so a cancelled reservation is not reported booked. Seven business tools plus native end_call are configured on both private provider candidates.

Evidence: 26 actual model intent checks (19 initial plus 7 held-out checks, including negation and cancellation questions) passed; these are bounded synthetic checks, not universal accuracy or human ratings. An actual model + isolated PostgreSQL integration saved a natural-language booking, cancelled it and safely replayed the cancellation. No production booking was created by those checks. Original caller timestamps, playback completion and early/missing/changed evidence rejections are covered by the integration suite. Classifier-only synthetic requests took 0.628–2.071 seconds in the initial batch; this adds a booking-decision step and does not prove lower handset latency.

All twelve physical attempts are used, with zero remaining. The gateway is paused, UK campaigns remain disabled and no thirteenth call is authorised. A fresh handset booking/cancellation/latency test remains necessary; no human-equivalence or production-readiness claim follows from these repairs.

The semantic decision requires `BW_OPENAI_API_KEY` in the London API environment in addition to the private ElevenLabs agent/webhook configuration. It is never sent to the browser or India voice gateway. Missing key, model timeout or invalid structured output yields an unavailable result with no booking write. There is no fallback to a yes-word whitelist in the deployed managed gateway when a valid proposal is being confirmed. The unchanged legacy cascaded adapter retains its older confirmation policy.

Readback recovery is bounded per proposal in the session state: the first incomplete readback may be corrected once; a second failure returns a non-retryable booking-unavailable result and must not ask for another agreement. Cancellation removes the appointment from the office's confirmed-work views while retaining its audit record and cancelled booking row.
