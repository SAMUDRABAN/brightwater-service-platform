# Observed validation

6 November 2026 (Asia/Kolkata). These results describe an engineering release candidate, not approval to call customers.

| Check | Observed result |
|---|---|
| Native PostgreSQL integration suite | **117 passed in 12.49 seconds**, including current caller-turn correlation and superseded readback tests |
| Backend Ruff | Passed on source and tests |
| Office authentication suite | **8 passed**; expiry, tampering, rotation, redirects and same-origin checks |
| Next.js production build | Passed with TypeScript and the four real voice audition players |
| Linux container suite | **117 passed in 33.76 seconds** on isolated PostgreSQL 17/Redis 7.4 on the London host |
| Public deployment | One approved DigitalOcean London host, public HTTPS office/API, real PostgreSQL/Redis/Celery/Beat |
| TLS and access | Public TLS verified without bypass; unauthenticated dashboard 401; metrics unavailable externally; database/broker/app internal ports not reachable externally |
| Login/logout | Actual browser form login and sign-out exercised on the deployed predecessor; secure, HttpOnly, host-only, SameSite Strict session attributes verified without publishing cookie values |
| Worker and scheduler | Actual worker ping PONG; second Beat process rejected by database ownership lock |
| Database recovery | Actual dump restored into an isolated temporary restore database; eight fixture customers recovered; original database untouched |
| Off-host backup | Encrypted dump copied locally; authenticated decrypt round-trip passed; key kept outside source/deliverables |
| Operational data | Eight explicitly labelled assessment customers, zero calls, dialing disabled in configuration and database |
| Provider availability | Supplied account credentials authenticated; bounded OpenAI Realtime text request returned expected response |
| Voice auditions | Four real ElevenLabs Flash v2.5 British voice clips; independent transcription recovered selected date/diary phrases in all four |
| Native turn models | Local EOT/VAD models loaded and ran a silence prediction; this is not conversational evaluation |

The backend suite covers calling windows/DST/preferences, UK-only destinations and fictional-number rejection, disabled dialing, scoped identity/account access, suppression, duplicate events, outcome precedence, multi-property pricing/tenants, interrupted and stale confirmations, delayed transcript capture, new-turn invalidation, competing PostgreSQL booking transactions, outbox/idempotency, uncertain provider outcomes, encrypted media and knowledge boundaries. Fixtures never dial.

Original speech start time, rather than transcript receipt time, is used for caller evidence. Duplicate SDK delivery paths share one event. Beginning a new caller turn invalidates the prior confirmation immediately. A readback of a different proposal invalidates the previous proposal. Missing verified speech timing fails closed for booking. A narrow whole-utterance opt-out detector also persists suppression with the transcript, without a model tool or verified identity. Clear commands, duplicate delivery, negation and quoted phrases have integration tests. It is not a general intent classifier. These are tested control-plane safeguards; their integration with real handset audio still requires qualification.

## Historical pre-call limits

At that initial checkpoint, no real phone call had been made. Voice naturalness, conversational flow, audible interruption timing, recording completeness, actual carrier lifecycle and the six assessment calls remain **NOT EVALUATED**. The sample clips are clean TTS auditions, not MOS or conversation results. OpenAI native audio is a separate lab comparator and is rejected by the normal worker factory because the installed SDK does not provide the required deterministic opening/readback/safety speech path.

The London host is a single point of failure. An encrypted off-host dump plus one successful isolated restore is not HA, PITR or a complete disaster-recovery drill. Remote GitHub Actions, load/failover/rollback under calls, SSO/MFA, external diary integration, retention/deletion and independent safety detection remain outstanding.

The current Plivo account has an Indian number; UK inventory returned no available number. The supplied attended recipient is also Indian. An India-to-India call through London media has not been established as a supported route, so no domestic phone test is attempted through that architecture. UK campaign validation remains +44-only.

## Local environment repair

Documents filesystem reads stalled, and the initial local development PostgreSQL cluster under Documents reported an unreadable block. That interrupted run is not counted. A fresh isolated UTF8 cluster under `/tmp/brightwater-pg-okx20-v2` on loopback port 55433 was migrated and tested. Runtime/build staging is outside Documents. Existing system PostgreSQL/Redis services were untouched. Reproducible source archives are generated from a verified committed snapshot, not a potentially stalled working-tree traversal.

Direct voice gateway details and the actual synthetic provider/India-host checks are recorded in [voice-gateway.md](voice-gateway.md). No handset score is inferred from these checks.

## Individual staff authentication — 7 November 2026

Native PostgreSQL 16 suite: **215 passed in 39.17 seconds**, including 13 staff-access tests. Fresh migrations, staff-only downgrade/re-upgrade and preservation of eight fixture customers passed. Ruff passed. The four current frontend tests cover opaque-cookie syntax, safe returns and form/canonical origins; expiry and revocation are now tested against the API/database. The Next.js production build passed. Linux and deployed acceptance results are recorded separately after they run. This replaces the historical shared-login checks above for the new release.

[Staff access](staff-access.md) documents the permission matrix, bootstrap, reset/disable flow and remaining SSO/MFA limitations. No phone call was placed for this change.

The same committed staff release passed **215 tests in 102.63 seconds on isolated Linux/PostgreSQL 17/Redis 7.4**. Live acceptance passed **115 checks** across all six accounts: initial-password gate, password changes and session invalidation, role API denials, role-specific office rendering, team controls, Sarah's restricted system view, logout, forged-cookie denial and public endpoint protection. All acceptance sessions were revoked and all six accounts rearmed for a personal password change at handover. Eight fixture customers and ten prior engineering calls were preserved; no new call was placed.

The public login rendered in gstack Chromium with no console errors. No passwords were entered through browser automation; authenticated rendering was checked through the owned application's HTTP integration tests. The deployed web container was inspected for credential names and contains no shared office password, operator token or voice-provider keys. API and office release: `9c3bc10239f23e2e80d57ca55bb82d147cd40ee4`; voice remains `f82759f92c71bcb6e04c384ddba0e19b3c61cfba`; worker/Beat remain `f98f9671cb6507fee2a28fe919bcaeb827d437e4`.


## Conversation and audio-onset update — 7 November 2026

Final native suite: **229 passed in 38.91 seconds**. Isolated Linux/PostgreSQL 17 suite: **229 passed in 114.14 seconds**. Ruff passed. Four current frontend tests and a production build passed for the Quality-page audition update. The actual deployed India container passed Lily/v4 Turbo output through the mu-law bridge with simulated playback acknowledgements and SDK speaking-state observation. Real STT/GPT/TTS replays used only the isolated test business API; they verified identity, original speech timing, phase transition and outbound purpose. No carrier call or production business write occurred.

The old bridge omitted `playback_started`, leaving the SDK in thinking state during speech. The fix signals start only after a sent-frame carrier checkpoint ACK; tests cover no queue-time start, duplicate ACKs, a second segment, actual SDK speaking-state transition and interruption/clear. Conservative ACK observation is not human hearing proof. A short replay still hit the three-second semantic maximum, so this release does not claim all pauses resolved. See [conversation improvement](conversation-improvement.md) for failed prompt comparisons, component timing limitations, current selected voice, the realtime lab candidate and handset gates.

## Native ElevenLabs candidate, 7 November 2026

The first managed integration release passed 261 backend tests natively and on isolated Linux/PostgreSQL17, plus the four frontend session tests and production build. The subsequent closing correction adds a regression for preserving a completed booking on tool retry; targeted managed tests pass 26 cases. Genuine provider tests use fictional accounts and a separate PostgreSQL database, not stub tools. Both failed and successful engineering evaluations remain retained. Voice-mode reservation commits remain explicitly unqualified and blocked; no new telephone call was placed.

The closing service correction passed all **262 native tests (71.43 seconds)** and **262 isolated Linux/PostgreSQL17 tests (117.31 seconds)**. Final managed provider-registration checks pass **26 targeted tests**. The official browser SDK build and four frontend session tests pass. Native provider tests preserve both the timed-out ending and the later `Booked` + `end_call` result. See managed-voice-candidate.md for distinctions between real provider integration, synthetic audio timing and unmeasured handset quality.

## 7 November: owner-conversation repair and managed Plivo adapter

Current committed runtime `42957e9e6eff879b62df4519f8c5f6882adee9db`: **293 native tests passed in 78.89 seconds**; **293 isolated Linux/PostgreSQL17 tests passed in 127.07 seconds**. Ruff and whitespace checks pass. The targeted managed-phone suite contains 31 cases. Frontend source did not change; its prior four session tests and official-SDK production build are not represented as newly rerun.

Tests cover the owner's exact repeated affirmative replies, honest recovery when saving is unavailable, mandatory postcode, spoken-number equivalence with wrong-detail rejection, original packet timestamps, final carrier ACK versus queued audio, interrupted readbacks, main engineering booking/idempotency, cross-database separation, dual runtime/call authentication, destination allowlisting, preservation of Plivo identifiers, and eight simultaneous readers racing an independent evidence writer. No local test contacts a telephone destination.

Actual GPT-4.1 passed three synthetic recovery/closing checks. Actual authenticated Plivo GET confirmed ownership of the configured Indian caller ID without changing its application. An actual ElevenLabs audio session with synthetic caller input and simulated paced carrier ACKs recovered complete speech and the correct due service. Two earlier audio/alignment failures are preserved. The passing trace's caller onset preceded observed final playback ACK by 11 ms, which the strict main-phone identity gate would reject; no phone booking success or handset timing is inferred. See managed-voice-candidate.md.

This change adds no physical call: eleven attempts remain used of eleven. The India gateway selects native ElevenLabs and is paused. UK campaigns stay disabled. Browser voice booking remains unqualified and blocked, while text evaluations use their separate restricted database. Main-diary managed phone booking is implemented behind original-speech and playback checks and remains awaiting attended qualification.

## 8 November: semantic booking/cancellation release

The final source passes **314 native tests in 75.67 seconds**; 21 final intent/cancellation/recovery regressions pass, including exact spoken postcode/year, real policy booking, fresh original evidence, withdrawal/correction, proposal-bound proof, no resurrection after cancellation, once-only capacity release and removal from confirmed office work. Ruff and whitespace checks pass. The full Linux/PostgreSQL17 check uses the exact committed source mounted read-only and verifies the dependency-image lock before execution; its final result is recorded with deployment below. Earlier 313/314 intermediate Linux results are retained separately and do not stand in for that final check.

Twenty-six actual server-model intent checks passed across initial and held-out batches. Four actual GPT-4.1 tool-selection checks chose the correct current proposal and booking/cancellation action for natural assent, the owner's wording, cancellation and negated cancellation. An actual semantic-model plus isolated PostgreSQL integration saved and cancelled a reservation with safe retry; no production write or phone call was involved. These are bounded integration checks, not universal intent accuracy or handset quality scores.

The twelfth actual phone attempt completed identity and full readback but booked nothing because spoken postcode digits were added together. Its original agreement followed completed playback by 1.684 seconds. The caller confirmed hanging up due to the repeated details; its recording is available. Matcher, contextual intent and bounded recovery repairs are implemented. Twelve of twelve physical attempts remain used, gateway admission is off and no thirteenth is authorised. Browser voice booking remains unqualified and blocked; telephone booking still needs fresh attended end-to-end qualification.

Final Linux source `014fdc1e768f21ef113ca5f304dcb27cc62dab45` passed **314 tests in 129.32 seconds**. The deployed API's actual synthetic model checks returned confirm/change/cancel with no database write. Both provider candidates retained their eight-tool configuration. Live preservation/access checks confirm twelve retained calls, zero office bookings, no active call, a free managed lease, UK controls off and paused phone admission.

## Native quality rollout — 8 November

Runtime `0b70e9764a3d90a111fc0bc4fe8a619885a6bea9` passed **316 native tests in76.66s** and **316 Linux/PostgreSQL17 tests in129.56s**. The final tool-description/prompt and test-reference recovery changes passed80 targeted managed cases in12.57s. Ruff/whitespace checks pass. Frontend source was unchanged.

The final provider configuration passed18/18 native phone-agent runs,3/3 browser-agent checks and3/3 targeted authorization-recovery repeats, with independent strict generated-proposal checks in the runner. Native tests use synthetic contexts and do not authorise office business writes. Failed pilots and intermediate failures are retained. See elevenlabs-quality-and-sip.md for exact scope, acoustic probes, the rejected phone backchannel setting, provider-reported stage metrics and inactive SIP preparation.


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


Post-activation verification passed: both public services ready, current API/model/voice revisions verified, anonymous managed/tool/runtime/stop requests rejected with401, authenticated stop for an unadmitted synthetic ID rejected with404, and unauthenticated office access redirected. Fourteen retained calls, zero office bookings, zero active calls, free managed lease, unchanged14 allowance, and both UK config/database controls off were checked. A real model request inside the deployed API returned confirm on a synthetic request without a database write or call.


## Fifteenth call and pause update — 9 November 2026

The fifteenth attended call saved one fictional engineering booking and ended normally. The owner reported smooth conversation with long pauses. The later deployed update uses truthful lookup acknowledgements and removes a redundant finish-tool round trip after a saved phone booking. Controlled diary-check first speech was 1.243s versus 4.116s; this is non-phone acknowledgement timing, not an end-to-end handset score. 355 native and 355 Linux tests pass. Raw native judgments 20/21 include one retained evaluator error; see the report. All 15 attempts are used, calling is paused, the booking/recording are preserved and no further call is authorised. A fresh handset latency check is still needed.

See [call15 and pause reduction](call15-booking-and-pause-reduction.md) for exact scope, timings, retained failures and deployment revisions.

## Latest attended result: call16

The owner confirmed the service disconnected. Carrier and gateway evidence identify an API-requested hang-up following a playback-checkpoint timeout. No booking was created. Calling is paused at16/16 used; the prior successful booking remains. Diagnostic evidence capture is improved, but the actual carrier failure and identity-onset association are unresolved. See [call16 investigation](call16-service-disconnect.md).

## 10 November: attended phone duration

Runtime011e033 passes384 native tests108.65s and384 Linux/PostgreSQL17 tests177.97s; four office tests and production build pass. Native phone/API/gateway use7200sec, browser evaluations180sec. Generated20-minute stereo codec/encrypted-storage check passed; no new phone call. See [duration evidence](attended-test-duration.md).


## Contextual purpose controls — 10 November 2026

Dynamic purpose interpretation now covers persistent targeted harassment/unrelated chat and clear automated answerers. Fresh original caller evidence and an actually played conditional warning protect genuine enquiries; callbacks, quotes, complaints, safety issues and identified arrangement requests take precedence over conflicting conduct labels. A server-controlled Valory/v4 Turbo goodbye precedes carrier hangup when audio succeeds; provider failure has a bounded fallback. Normal voice/turn settings and business consent remain unchanged. See [policy, edge cases and retained evaluation results](call-purpose-boundaries.md).

Runtime `87f35241103981826d49915d3c43c6c68afa402b` is deployed to the API and India gateway. 410 native backend tests passed in 58.18 seconds; 410 Linux/PostgreSQL17/Redis backend tests passed in 186.22 seconds. No new phone call: 20/20 attempts used, admission/UK campaigns off, both existing bookings preserved. Handset qualification and the prior confirmation-loop/unsaved-office-help findings remain open.


## CRM release 0.2.0 — 10 November 2026

427 native backend tests passed in 63.49 seconds against isolated PostgreSQL16 and Redis. Ruff passed. Eight frontend tests, frozen dependency installation, formatting, TypeScript and the production Next.js build passed. GitHub CI is configured to repeat the backend suite on PostgreSQL17 and Redis7.4; only a completed CI run qualifies that environment.

A real Chromium browser checked 15 production-build desktop/mobile views against an isolated, explicitly labelled interface-fixture database. No page overflow remained at 390px; the production console reported no errors. Resolve/reopen follow-up actions and a customer's preferred contact time persisted through actual forms. Dan's engineer session opened his own booking without office navigation; cross-engineer and office restrictions are covered by API tests. A staff-authenticated CSV download succeeded, with formula neutralisation tested. Timestamps are exported as UTC and displayed in Europe/London.

The visual review used the supplied logo, Brightwater navy/orange palette and locally served licensed Manrope/Inter fonts. Screenshots are interface evidence, not phone-conversation evidence. Review fixtures were not copied to production.

No phone calls were placed. Existing 20 attempts and two engineering bookings remain the voice evidence baseline. UK PSTN qualification, six distinct assessment scenarios, the prior confirmation-loop/unsaved-office-help findings and the voicemail brief discrepancy remain open; see [assessment coverage](submission/assessment-coverage.md). This CRM release is not a claim that all assessment or production-readiness gates passed.
