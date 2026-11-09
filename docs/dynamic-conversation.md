# Contextual conversation interpretation

9 November 2026. This changes the managed ElevenLabs route, not the older unused cascaded adapter. Calling remains paused; fourteen attempts have been used and this work authorises no additional call.

## What changes

The caller does not need one of a fixed list of phrases for identity, booking, cancellation, callbacks, quote interest, complaints or urgent reports. Server-owned structured interpretation reads the whole latest reply and its trusted conversation context. It also recognises natural wrong-number, recording-refusal, stop-contact and speaker-change requests. Booking and cancellation explicitly resolve whether the request concerns this arrangement or another/historical visit. Different or unidentified appointments cannot be cancelled as this proposal.

ElevenLabs still runs speech recognition, native conversation generation/turn taking and Lily/v4 Turbo speech. A separate GPT-4.1 interpretation verifies intent before business tools act. It is not an agent-supplied confirmation flag. The previous GPT-4.1-mini booking-only classifier remains a legacy module; the selected managed gateway uses the contextual path. Server GPT-4.1 is configured independently from ElevenLabs' conversational GPT-4.1.

Complete booking facts may be phrased naturally. A deterministic factual matcher remains a fast path for already supported readbacks. Other wording uses blind structured extraction from the actual completed speech: expected proposal values are not supplied to the extractor. Extracted address, postcode, service, date, arrival window, total, VAT and payment are compared with the authoritative proposal, with verbatim source quotes. A known format is no longer an exclusive acceptance requirement.

## What remains enforced

Identity/notice, original caller speech timing, actual completed carrier playback, interruption/handoff invalidation, fresh current replies, customer/proposal binding, proposal expiry, suppression, diary capacity, authorisation and idempotency remain backend checks. Named self-identification needs grounded name evidence; unnamed assent depends on the current completed identity question. A callback answer depends on an actual completed offer; refusal cannot be overridden by pressured contextual agreement. Reported urgent/emergency issues block routine booking. Advice must precede tools.

Narrow deterministic stop/refusal backstops remain additional privacy protection; they are not the only wording understood. Natural stop/refusal controls revoke account access and end only the existing admitted call through an authenticated, call-bound stop endpoint. No phone number/carrier ID is accepted from the model. The route cannot dial. Carrier stop submission is not proof of a completed hangup; signed lifecycle events remain authoritative.

The unused cascaded/legacy adapter retains its old policy helpers. This change does not claim every repository regex was removed. Fixed business facts and safety rules deliberately do not become model guesses. Browser voice booking remains unqualified and blocked. A customer question, correction or interrupted readback still requires an appropriate complete current readback and fresh authorisation before booking; this release does not implement a long-lived consent grant across intervening questions.

## Timing and failure behaviour

Trusted caller-event ingestion prefetches interpretation to overlap it with native agent generation. Completed speech prefetches factual extraction before the caller answers. Short reply interpretation and uncached extraction can run concurrently. Redis caches/singleflight are scoped to exact source events, text, question, customer, proposal/fingerprint and context. Inference happens outside SQL/control locks; context is checked again under the action lock. No old decision grants a new action. Optional caching failures do not grant permission. Model/schema/timeouts fail closed with an honest unavailable response, not a demand to repeat a special yes phrase.

## Evidence

The initial combined-model experiment failed 21 of 38 strict-label checks, including actual unsafe interpretations of quoted identity and callback questions and factual-extraction timeouts. It was retained privately, not presented as a pass. After separating jobs, improving the boundaries and adding independent current-arrangement/name/playout gates, GPT-4.1 passed all 57 action-level synthetic text checks (51 exact internal-label matches). Median total interpretation/extraction time was 0.958s, maximum 1.851s in that run. Safe differences such as declining versus unclear do not authorise a write; those are counted separately from exact label agreement.

These bounded text regression experiments do not measure handset latency, voice naturalness or production error rates. Existing failed calls/recordings remain preserved. Final unit/integration/Linux/native-provider results and deployed revisions are recorded in validation and release readiness after verification. Fresh attended identity, saved booking/cancellation, interruption and latency qualification remains necessary. UK route/consented destination and the broader production gates remain open.


The final integration check used the real model with the isolated local test database and explicitly synthetic carrier events. It verified identity and notice, rejected a spoken £195 against a £95 proposal, saved the correctly read £95 booking on natural authorisation, rejected cancelling a different historical visit, and cancelled the current saved visit. Availability/preparation reused the interpretation in 3–5ms; uncached interpretation/extraction took 1.128–1.787s in that sequence. No production diary write or phone call occurred. An earlier failed probe with malformed pound-sign quotes is retained; unescaped Unicode input and strictly grounded source quotes repaired it. Identity-question quotes are also grounded in the actual current completed question, not a question from earlier history. Incomplete notices now produce a truthful notice-recovery instruction rather than another unexplained name loop.

The same pre-release 57-case comparison returned 57 action-level passes with GPT-4.1 versus 48 with GPT-4.1-mini (medians 0.958s and 1.434s respectively). This is a small synthetic comparison used to select the default, not an estimated production accuracy rate. Later diagnostic runs and failures remain retained alongside the final release regressions; the corpus informed improvements and is not an independent statistical holdout.


## Verified release

The managed ElevenLabs route now uses server-owned GPT-4.1 contextual interpretation for identity, natural booking/cancellation, follow-ups and stop/privacy requests, rather than a required list of acceptance phrases. Naturally phrased readbacks are extracted from actually completed speech and checked against the authoritative booking facts. Current-question/name quotes, original caller timing, played notice, interruptions, customer/proposal binding, expiry, capacity, permissions and idempotency remain enforced. Interpretation is prefetched and cached by exact context; factual extraction overlaps speech/caller response. Model failures do not save changes or demand another special yes. 355 native tests passed in 52.57s; 355 isolated Linux/PostgreSQL17 tests passed in 177.84s; Ruff/whitespace passed. 57 real-model action regressions and 12 new held-out synthetic text cases passed. 18 native phone-profile and 3 browser-profile regressions passed, with generated-parameter checks. The actual model plus isolated test database verified identity, rejection of a wrong price, saving a natural-language booking, refusal to cancel a different visit and cancellation of the current booking. API and India voice runtime 56c5e43799d40d56abf28427a989c030b71f7f4e are deployed healthy; office/worker/Beat and the unrelated Bangalore server are unchanged. Calling remains paused, 14/14 attempts used, 0 remaining, no active call, UK controls off and no extra phone call placed. Phone booking, cancellation, interruptions, perceived voice quality and end-to-end latency still require fresh attended handset qualification. Current readback validation does not grant reusable consent across intervening questions. Native SIP remains disabled/unassigned; no production-readiness claim is made.

The final 57-case regression run had median 1.017s and maximum 2.236s for synthetic interpretation/extraction, excluding handset transport and native conversational generation. The additional 12 cases were written after the prompt was pinned and all passed. All intermediate diagnostic failures remain private audit evidence.


Post-activation verification passed: both public services ready, current API/model/voice revisions verified, anonymous managed/tool/runtime/stop requests rejected with401, authenticated stop for an unadmitted synthetic ID rejected with404, and unauthenticated office access redirected. Fourteen retained calls, zero office bookings, zero active calls, free managed lease, unchanged14 allowance, and both UK config/database controls off were checked. A real model request inside the deployed API returned confirm on a synthetic request without a database write or call.


## Fifteenth call and pause update — 9 November 2026

The fifteenth attended call saved one fictional engineering booking and ended normally. The owner reported smooth conversation with long pauses. The later deployed update uses truthful lookup acknowledgements and removes a redundant finish-tool round trip after a saved phone booking. Controlled diary-check first speech was 1.243s versus 4.116s; this is non-phone acknowledgement timing, not an end-to-end handset score. 355 native and 355 Linux tests pass. Raw native judgments 20/21 include one retained evaluator error; see the report. All 15 attempts are used, calling is paused, the booking/recording are preserved and no further call is authorised. A fresh handset latency check is still needed.

See [call15 and pause reduction](call15-booking-and-pause-reduction.md) for exact scope, timings, retained failures and deployment revisions.
