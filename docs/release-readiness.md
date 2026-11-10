# Release readiness: engineering candidate deployed

The business control plane and office are deployed on one approved London host. Customer calling remains disabled. This is not a production-qualified voice service.

## Priority and selection

Voice quality and conversation quality retain **70%** of the selection score: voice 35%, conversation 35%, task correctness 15%, operations 10%, total cost 5%. Hard safety/privacy/action gates cannot be averaged away. No missing metric is scored as zero, and no vendor claim substitutes for measurement.

Implemented phone-worker candidates: direct OpenAI Realtime text with ElevenLabs TTS, or cascaded OpenAI STT/LLM with ElevenLabs TTS. The hosted inference branch remains optional. Direct mode uses local semantic endpointing, Silero VAD and VAD interruptions; hosted adaptive interruption classification is not claimed. OpenAI native audio is lab-only because deterministic opening/readback/safety scripts are unsupported by that path in the installed SDK. ElevenLabs Agents now provides the managed conversation path over the existing authenticated Plivo stream; it is not handset-qualified.

Four actual British voice auditions are available in the Quality view. No winner is selected. Run a preregistered handset comparison using independent consenting participants and held-out cases; version code, prompt, knowledge, model, voice, codec, carrier, region and settings. Keep failed calls. Report uncertainty by participant, not repeated turns as independent people.

Proposed, unachieved targets: voice and interaction means ≥4.2/5, 95% lower bounds ≥4.0; routine handset reply p50 ≤800 ms/p95 ≤1,500 ms; genuine interruption audible-stop p95 ≤300 ms; premature endpoints ≤2%; false stops ≤5%; correction recovery ≥95%. These need pilot calibration and are not certifications.

## Work remaining before real customer production

1. Establish an authorised UK carrier route/caller ID and consented UK recipient. Existing Indian Plivo number and Indian test recipient do not qualify London-mediated India domestic audio. UK inventory is unavailable on the current account. Do not alter the unrelated Bangalore host or route around this uncertainty.
2. Qualify the deployed direct Plivo India engineering gateway: attended lifecycle, provider events, recording/transcript completeness, playback and scoped booking end to end. LiveKit Cloud/SIP is not required by this roomless path. Configure the actual office callback and supported UK route before UK qualification. The first six attempts failed before agent speech; call 7 established clear two-way handset audio but a name-confirmation loop. Call 8 exposed colloquial-confirmation and transfer-language defects; fixes are deployed. Call 9 reached a busy line. The tenth call passed identity and outbound purpose but failed natural booking confirmation and recorded a callback. The booking repair still needs handset verification; see voice-gateway.md and the current manifest.
3. Measure listening, semantic endpoints, genuine/false interruptions, corrections, digits, quiet/older voices, accents, noise and silences. A narrow independent whole-utterance opt-out backstop now persists suppression atomically with the transcript. Broader safety/opt-out detection and failed event-capture handling still need qualification. Advice now begins before its database write completes, but audibility is not yet established on a handset.
4. Run all six assessment scenarios and the full outcome/privacy/suppression/safety matrix as real consented calls. Preserve recording, transcript, action and provider identifiers. Unit fixtures and clean voice auditions do not satisfy these calls.
5. Complete attended activation, SSO/MFA and expanded access review, audit review, follow-up resolution and authoritative carrier reconciliation. Unknown initiation outcomes remain quarantined rather than blindly redialled.
6. Integrate the actual business diary/customer source and validate absences, holidays, travel, renewals, cancellation/rescheduling and landlord alternatives. Assessment availability is labelled fixture data.
7. Add independently isolated staging/shadow/production and recovery infrastructure when budget permits. The user approved a $24/month London business host and a separate $12/month India voice host. These different roles do not establish a mirror or failover pair. Current temporary checks use their own internal network/database and are removed after testing. One host cannot establish HA or independent mirror recovery.
8. Complete retention/deletion, backup-key custody, scheduled off-site backups, restore drills/RPO/RTO, monitoring/alerts, budget alarms, load and graceful call draining. An isolated restore passed; disaster recovery is not qualified.
9. Run remote CI and a real rollback rehearsal before live activation. Recordings and credentials must be retained across releases. Rotate chat-exposed provider keys before customer production.
10. Finish the measured cost note and assessment handover from actual calls. Combined incremental compute is $36/month before tax; backups, provider usage and future independent infrastructure are separate. No unapproved additional resource is implied.

One owner reported clear handset speech; this is not an independent quality score. Conversation qualification, latency distributions and the full scenario matrix remain incomplete. Independent backend speech-timing verification now guards booking commit; complete the held-out confirmation and failure matrix before production. Voice/conversation statistical measures remain **NOT EVALUATED**. Natural delivery is a goal, not evidence of human equivalence or perfection. The agent must not falsely claim to be human or impersonate an employee.

Latest latency work combines verified identity and account context, avoiding one model/tool roundtrip. Numeric stage timings are now captured in bounded local Redis records. Owner feedback still flags pauses; do not treat the request-count improvement as a handset response-time pass. Fresh attended booking and latency qualification remain required.

Individual staff identities, forced initial password changes, revocable sessions, server-side role enforcement and administrator reset/disable controls are now implemented and deployed. See [staff access](staff-access.md) and the current validation evidence. This closes the shared-login/role-separation gap; SSO/MFA, independent security review and broader production qualification remain outstanding.

## 7 November: native managed candidate

An administrator-only ElevenLabs candidate is being qualified using a separate PostgreSQL evaluation database and native server tools. See `managed-voice-candidate.md`. The failed eleventh attended Plivo call remains a failed call; all eleven phone attempts are used, with no twelfth authorised. Local managed text booking evidence does not qualify voice-mode or phone-mode booking confirmation, which remains blocked in this candidate. The same Indian carrier route now feeds the managed conversation adapter. It remains paused; neither provider configuration nor synthetic audio checks authorise another call or qualify UK campaigns.

## Managed Plivo integration: current gate

The existing Indian Plivo number is wired to the native ElevenLabs conversation backend through the authenticated streaming gateway; no SIP number import or replacement carrier is required. Carrier recording, original caller packet timestamps, completed-playback ACKs, identity/privacy, booking idempotency and call limits remain enforced. Browser history is never promoted to original speech evidence. Backend tests exercise a main-diary engineering booking with original evidence, plus early, interrupted, unverified and incorrect-readback rejections.

No twelfth phone call is authorised. The native adapter is deployed with gateway admission off and eleven of eleven physical attempts used. The managed phone booking branch is implemented, but full handset identity/booking/end-call and actual interruption/latency verification remain required. Browser voice commits continue to fail closed; clear agreement is now acknowledged honestly when a technical restriction prevents saving.

## 8 November: dynamic booking and cancellation

The managed path now interprets current intent semantically rather than requiring one of a small list of yes phrases. Spoken postcode/year matching is repaired. Current-conversation cancellation releases actual diary capacity idempotently. Model uncertainty/unavailability cannot save an arrangement. Historical appointments are not guessed. See managed-voice-candidate.md for the failed twelfth handset call, owner-confirmed hangup, exact evidence and model/DB checks. Twelve of twelve physical attempts are used; the gateway remains paused and no thirteenth is authorised. Full handset booking, cancellation, interruption and latency qualification is still outstanding.

## Native quality settings and SIP candidate

The quality package is deployed and its final native behavior regressions pass. This does not establish measured handset voice/conversation quality. See elevenlabs-quality-and-sip.md. The phone acknowledgement filter was tested and withheld because it conflicted with trustworthy original onset mapping; the split-ASR observer repair is deployed.

The number is now registered in ElevenLabs with a disabled secure outbound trunk and no assigned agent. Direct SIP has not replaced the bridge. Before cutover, qualify the native caller route, scope/lifecycle binding, encrypted recording ingestion and an equivalent speech/playback consent contract. TLS/OPTIONS is not call/booking qualification. Twelve of twelve attended attempts remain used. No thirteenth or plan upgrade is authorised by configuration work.


## Final audio protocol release — 8 November 2026

India gateway runtime `d84ff588d1a1a56dd6dc0120a48c041a44077434` is healthy and paused. Exact runtime code passed319 native tests in79.90s and319 isolated Linux/PostgreSQL17 tests in130.39s. The final package additionally sorts two existing migration imports; backend/script Ruff and whitespace checks pass. London API remains `014fdc1e768f21ef113ca5f304dcb27cc62dab45`; office and worker/Beat are unchanged.

The final real-provider, simulated-carrier audio probe completes both tool acknowledgements and the full booking readback. Cumulative caption/audio handling preserves speech that starts before its text event and freezes prior playback proofs. No reservation was committed and no physical call was placed by that probe. Earlier failed probes remain retained. Native phone18/18 and browser3/3 checks remain the final provider configuration checks; they are not handset-quality or saved-booking evidence.

The imported SIP number remains unassigned with its secure trunk disabled and the existing Plivo application unchanged. The current bridge remains selected; twelve of twelve phone attempts are used and no thirteenth is authorised. Read the full limitations in elevenlabs-quality-and-sip.md before any handset verification or SIP cutover.


## Attempt13 playback investigation — 9 November 2026

The thirteenth attended call failed to save a booking despite recognised agreement and was disconnected by the service. A reproducible playback-flush race and silently completed transport-failure path are repaired in61fd39f; the precise past trigger was not retained. See [call13-playback-investigation.md](call13-playback-investigation.md) for actual carrier/recording evidence, before/after regression and deployment.13of13attempts are used, no further call is authorised and calling remains paused. Earlier provider tests and synthetic audio checks remain engineering evidence; they do not qualify handset booking.


## Speech detector cause confirmed — 9 November 2026

The previous 8 kHz detector found no caller speech in the saved call; the 16 kHz detector found five starts without lowering its threshold. The repaired bridge mapped all five to original carrier times, and the owned profile was corrected to the supplied full name. Voice runtime6b29593 is deployed and paused;326native/Linux tests pass. See [speech-detection investigation](call14-speech-detection-investigation.md) for exact evidence and limits. Fourteen attempts remain used, no further call is authorised, and fresh handset booking is still unqualified.


## Contextual ElevenLabs conversations — 9 November 2026

The managed ElevenLabs route now uses server-owned GPT-4.1 contextual interpretation for identity, natural booking/cancellation, follow-ups and stop/privacy requests, rather than a required list of acceptance phrases. Naturally phrased readbacks are extracted from actually completed speech and checked against the authoritative booking facts. Current-question/name quotes, original caller timing, played notice, interruptions, customer/proposal binding, expiry, capacity, permissions and idempotency remain enforced. Interpretation is prefetched and cached by exact context; factual extraction overlaps speech/caller response. Model failures do not save changes or demand another special yes. 355 native tests passed in 52.57s; 355 isolated Linux/PostgreSQL17 tests passed in 177.84s; Ruff/whitespace passed. 57 real-model action regressions and 12 new held-out synthetic text cases passed. 18 native phone-profile and 3 browser-profile regressions passed, with generated-parameter checks. The actual model plus isolated test database verified identity, rejection of a wrong price, saving a natural-language booking, refusal to cancel a different visit and cancellation of the current booking. API and India voice runtime 56c5e43799d40d56abf28427a989c030b71f7f4e are deployed healthy; office/worker/Beat and the unrelated Bangalore server are unchanged. Calling remains paused, 14/14 attempts used, 0 remaining, no active call, UK controls off and no extra phone call placed. Phone booking, cancellation, interruptions, perceived voice quality and end-to-end latency still require fresh attended handset qualification. Current readback validation does not grant reusable consent across intervening questions. Native SIP remains disabled/unassigned; no production-readiness claim is made.

See [dynamic conversation evidence](dynamic-conversation.md).


## Fifteenth call and pause update — 9 November 2026

The fifteenth attended call saved one fictional engineering booking and ended normally. The owner reported smooth conversation with long pauses. The later deployed update uses truthful lookup acknowledgements and removes a redundant finish-tool round trip after a saved phone booking. Controlled diary-check first speech was 1.243s versus 4.116s; this is non-phone acknowledgement timing, not an end-to-end handset score. 355 native and 355 Linux tests pass. Raw native judgments 20/21 include one retained evaluator error; see the report. All 15 attempts are used, calling is paused, the booking/recording are preserved and no further call is authorised. A fresh handset latency check is still needed.

See [call15 and pause reduction](call15-booking-and-pause-reduction.md) for exact scope, timings, retained failures and deployment revisions.

## Latest attended result: call16

The owner confirmed the service disconnected. Carrier and gateway evidence identify an API-requested hang-up following a playback-checkpoint timeout. No booking was created. Calling is paused at16/16 used; the prior successful booking remains. Diagnostic evidence capture is improved, but the actual carrier failure and identity-onset association are unresolved. See [call16 investigation](call16-service-disconnect.md).


## Contextual purpose controls — 10 November 2026

Dynamic purpose interpretation now covers persistent targeted harassment/unrelated chat and clear automated answerers. Fresh original caller evidence and an actually played conditional warning protect genuine enquiries; callbacks, quotes, complaints, safety issues and identified arrangement requests take precedence over conflicting conduct labels. A server-controlled Valory/v4 Turbo goodbye precedes carrier hangup when audio succeeds; provider failure has a bounded fallback. Normal voice/turn settings and business consent remain unchanged. See [policy, edge cases and retained evaluation results](call-purpose-boundaries.md).

Runtime `87f35241103981826d49915d3c43c6c68afa402b` is deployed to the API and India gateway. 410 native backend tests passed in 58.18 seconds; 410 Linux/PostgreSQL17/Redis backend tests passed in 186.22 seconds. No new phone call: 20/20 attempts used, admission/UK campaigns off, both existing bookings preserved. Handset qualification and the prior confirmation-loop/unsaved-office-help findings remain open.


## CRM release 0.2.0 — 10 November 2026

427 native backend tests passed in 63.49 seconds against isolated PostgreSQL16 and Redis. Ruff passed. Eight frontend tests, frozen dependency installation, formatting, TypeScript and the production Next.js build passed. GitHub CI is configured to repeat the backend suite on PostgreSQL17 and Redis7.4; only a completed CI run qualifies that environment.

A real Chromium browser checked 15 production-build desktop/mobile views against an isolated, explicitly labelled interface-fixture database. No page overflow remained at 390px; the production console reported no errors. Resolve/reopen follow-up actions and a customer's preferred contact time persisted through actual forms. Dan's engineer session opened his own booking without office navigation; cross-engineer and office restrictions are covered by API tests. A staff-authenticated CSV download succeeded, with formula neutralisation tested. Timestamps are exported as UTC and displayed in Europe/London.

The visual review used the supplied logo, Brightwater navy/orange palette and locally served licensed Manrope/Inter fonts. Screenshots are interface evidence, not phone-conversation evidence. Review fixtures were not copied to production.

No phone calls were placed. Existing 20 attempts and two engineering bookings remain the voice evidence baseline. UK PSTN qualification, six distinct assessment scenarios, the prior confirmation-loop/unsaved-office-help findings and the voicemail brief discrepancy remain open; see [assessment coverage](submission/assessment-coverage.md). This CRM release is not a claim that all assessment or production-readiness gates passed.


## Call 21 latency candidate — 10 November 2026

The owner-initiated twenty-first call saved a third fictional engineering booking. Connection preparation now overlaps ringing and caption analysis overlaps readback speech; actual playback/current-reply authorisation remains unchanged. The prompt/opening are shorter and 17 native ElevenLabs prompt regressions passed. 441 native backend tests passed in 113.81s, plus final focused checks. Two new regressions fail on the prior code and pass after repair. Real-model factual analysis took 1.748s initially and 0.0006s on cache hit; this is not handset latency. No new call was placed and the configured allowance remains 21/21 used. See [latency evidence and remaining concerns](call21-latency.md).


## 10 November: call22 booking continuity

See [call22-booking-continuity.md](call22-booking-continuity.md) for the actual fourth fictional booking, retained22 attempts, engineer/date preferences, shared CRM read model and successful checks. This latest entry supersedes earlier attempt-count and paused-configuration checkpoints; ordinary UK customer calling remains disabled. No further handset call was placed or authorised by this release.


## Automatic reminders and screenshot brief audit

See [campaign-and-brief-coverage.md](campaign-and-brief-coverage.md) for the 28-day native ElevenLabs campaign, all screenshot requirements, policy/queue controls, remaining activation gates and evidence limits. Customer calling remains off, India remains an attended engineering route and no extra phone attempt is authorised.
