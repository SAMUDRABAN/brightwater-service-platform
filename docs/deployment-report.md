# Current deployment evidence

6 November 2026. Engineering candidate; UK customer campaigns disabled.

- Office/API: https://office.46.101.11.137.sslip.io / https://api.46.101.11.137.sslip.io . API release `f8dcf246026df82d54d3b0fbdf09dc1be68129cd`.
- India voice: https://voice.159.65.149.114.sslip.io . Voice release `f82759f92c71bcb6e04c384ddba0e19b3c61cfba`.
- Office, worker and fenced Beat retain unchanged source `f98f9671cb6507fee2a28fe919bcaeb827d437e4`. The API source has a separate api-current pointer.
- Approved additional compute: London $24/month plus dedicated India $12/month, before tax/usage. Existing unrelated Bangalore server untouched. No additional host authorised.
- Actual PostgreSQL 17/Redis/Celery/Beat/Caddy/Next/API and roomless voice gateway run on those hosts. UK campaigns remain disabled; only separately attended owner engineering calls are permitted.
- Native backend 202 passed in 21.97 seconds; isolated Linux/PostgreSQL 17 backend 202 passed in 53.03s; Ruff clean. Later call-ceiling-only changes were validated separately. Frontend source unchanged from its passing eight auth tests/production build.
- The seventh actual call established two-way audio, owner-confirmed clear speech and protected stereo recording playback. It did not pass conversation/task qualification. Eighth-call semantic failures were retained and repaired. Ninth call was carrier Busy Line without an answer. The tenth call passed identity and outbound purpose, reached booking readback, then recorded a callback when the older natural-consent parser rejected the reply. No booking was created. That parser, independent backend timing verification, confirmation-error handling and closing-playout ordering are now repaired; a fresh handset retest remains required.
- All eight earlier answered calls were reconciled against authenticated carrier CDRs. No answer fallback was corrected to unknown business outcome; original classifications remain in audit events. No booking was invented. The genuine busy-line attempt retains No answer.
- Four current-prompt actual-model text checks passed against synthetic fixtures; an earlier failed inbound-style response remains recorded. These do not substitute for handset conversation qualification.
- Public TLS and operator protection are active. Recording playback requires operator authentication and is encrypted at rest. API data/broker readiness and India gateway health are checked. API/DB/broker internal ports remain private.

Initial pre-call backup/isolated restore recovered eight fixture customers. That historical check is not a current-call-state restore, scheduled off-site backup system, PITR, failover or disaster recovery qualification. Provider/SSH/login/encryption keys remain outside the source package; the DigitalOcean token was not placed on the hosts.

[Voice evidence and fixes](voice-gateway.md) distinguish real calls, synthetic provider checks, model checks and unmeasured quality. [Remaining production gates](release-readiness.md) include supported UK routing, actual business integration, full call scenarios, independent conversation/voice evaluation, timing, SSO/MFA, retention/monitoring and recovery. This is not production-qualified.

The latest voice revision removes one redundant post-identity model roundtrip and adds bounded numeric latency capture. The owner still reports pauses; a handset timing recheck is outstanding. No new call has been placed after the tenth.

## Staff-access deployment — 7 November 2026

API and office now run `9c3bc10239f23e2e80d57ca55bb82d147cd40ee4`. `/opt/brightwater/api-current` and `/opt/brightwater/office-current` identify that release. The older `/opt/brightwater/current` still identifies worker/Beat source; use the service-specific pointers for targeted updates. The additive staff migration ran after a private pre-migration database dump. Six named accounts were bootstrapped without changing diary engineers or gas eligibility. Shared web authentication and the web operator-token environment were removed. Native and Linux suites both passed 215 tests; 115 deployed HTTP acceptance checks passed. All accounts require a personal password change; credentials stay outside this package. Voice, worker/Beat, call allowance, retained recordings and UK campaign controls are unchanged. No extra infrastructure or calls were created.

## 7 November: native ElevenLabs engineering candidate

London API runs `c8d74c41d5c89b95cb203dd1781dc50fa8f50322`; office runs `8a9c531010b53a24e3fcc9208ebcc9e6798df345`. The office uses official ElevenLabs client 1.35.0. Actual provider readback confirms Lily/v4 Turbo, signed access, six business webhook tools and a native system `end_call` tool. No telephone number is assigned to the candidate. The source provisioning configuration is newer than the API's runtime code and was applied directly through the provider API.

The dedicated restricted login owns only `brightwater_managed_evaluation`: eight fictional fixture customers, five native engineering evaluations and three stored evaluation bookings were verified. The login has no superuser/create-role/create-database flags and cannot select the office customers table. Office storage still has its eight fixtures plus the engineering customer, eleven prior phone calls and zero bookings. No new phone call was made. Anonymous candidate APIs and unsigned provider tools return 401. Office container inspection found no operator, runtime or voice-provider credentials.

Native tests finish a £95 booking and receive `end_call`; a continuously streamed synthetic audio check recovered the complete identity reply and returned the correct account/service. These are integration checks. Voice reservation confirmation, interruption behavior, listening ratings and the actual managed Plivo/UK route remain unqualified. India voice stays on `0325039d76cacdb82ac514c3cfe4eada62cc0706`; worker/Beat stay on their prior release. No staff passwords or sessions were reset, no host was added, and no UK campaign was enabled.

## Current managed Plivo release — 7 November 2026

London API and India gateway both run `42957e9e6eff879b62df4519f8c5f6882adee9db`, with verified healthy containers and public TLS. London office remains `8a9c531010b53a24e3fcc9208ebcc9e6798df345`; worker/Beat remain `f98f9671cb6507fee2a28fe919bcaeb827d437e4`. Only API and gateway containers were rebuilt/recreated; existing databases, brokers, recordings, staff identities and passwords were preserved. No migration or fixture reset was required.

The India gateway now uses native ElevenLabs via the existing authenticated Plivo streaming route. The carrier application/number is unchanged; authenticated read-only carrier API verified number ownership. This is a stream integration, not an imported ElevenLabs/SIP phone number, so provider `phone_attached` remains false while Brightwater `phone_route_configured` is true. Global OpenAI/ElevenLabs API keys were removed from the voice container's configuration; it obtains short-lived call-bound provider access through the London API. Private rollback configuration is retained outside the source package.

Deployed checks: API ready with UK dialing false; managed route configured, audio qualification false; gateway ready with `voice_backend=elevenlabs`, admission false. Physical attempts remain eleven of eleven, none active, zero remaining and zero office bookings. The shared managed lease is free. Anonymous managed status, unsigned native tool and unsigned runtime session requests all return 401; unsigned carrier answer/status/recording callbacks return 403; anonymous office access redirects to login. The existing provider candidates were updated in place and read back successfully with Lily/v4 Turbo and seven tools including native end_call. No host, number, subscription, call or staff reset was added.

The non-phone evaluation request bound is now twenty to permit retained diagnostic attempts; physical call allowance remains eleven and each provider agent retains a daily limit of ten. The user confirmed the split: India for phone audio, London for the app. All actual handset/booking/latency gates in release-readiness remain open. A twelfth attended call requires a fresh readiness reply and explicit bounded allowance; no automatic retry is configured.

## Contextual intent release — 8 November 2026

London API now runs `014fdc1e768f21ef113ca5f304dcb27cc62dab45`, healthy. India gateway remains `42957e9e6eff879b62df4519f8c5f6882adee9db` using native ElevenLabs; admission is paused. Office remains `8a9c531010b53a24e3fcc9208ebcc9e6798df345`, worker/Beat remain unchanged. The user confirmed India for phone audio and London for the app. No new host, number, subscription, staff reset, migration or fixture reset was applied to deployed data.

The twelfth explicitly authorised attended call used the managed carrier path and passed identity. No booking was saved: digit/year parsing rejected a correct completed readback and the owner hung up during the loop. The 138-second app-duration call and protected recording remain available. Its first agreement followed the completed readback by 1.684 seconds; original timing was verified. No thirteenth call is authorised.

Spoken digit/year matching, server semantic intent, current-arrangement cancellation, bounded readback recovery and confirmed-appointment filtering are deployed. Both provider candidates were updated in place and read back with Lily/v4 Turbo and eight tools: seven business tools plus native end_call. The London API has the private model key for independent contextual intent; the browser and India gateway do not receive that key. Three actual model requests from the deployed API correctly returned confirm/change/cancel using synthetic data with zero production writes and zero phone calls.

Final source validation: **314 native tests, 75.67 seconds**; **314 Linux/PostgreSQL17 tests, 129.32 seconds** with exact committed source mounted read-only and dependency-image lock verified. Production API image build and health passed. Twenty-one new intent/cancellation/recovery cases pass. Ruff and whitespace checks pass. No frontend source changed; earlier office tests/build are unchanged historical results.

Public TLS/auth/health checks pass. Main storage retains twelve engineering calls, zero bookings and no active call; physical allowance is twelve used of twelve. UK dialing config and campaign DB control remain false, shared managed lease is free and gateway admission is false. Browser voice reservation remains unqualified and blocked. Fresh handset booking/cancellation/interruption/latency qualification is still required. Current-arrangement cancellation is supported; unidentified historical appointments are an office task. This is an engineering candidate, not customer production qualification.

## Native quality and inactive SIP resources — 8 November

India gateway now runs `0b70e9764a3d90a111fc0bc4fe8a619885a6bea9`, healthy and paused, including the original-onset repair for split ASR. London API remains `014fdc1e768f21ef113ca5f304dcb27cc62dab45`; office/worker/Beat are unchanged. Both owned provider agents have the versioned quality configuration: dictionary, keyterms, nine native tests and six evaluation criteria. The balanced profile is restored; phone backchannel filtering remains off after its failed evidence probe. Final authorization-recovery prompt and refreshed native tool references are applied directly to the provider. No DB migration or staff reset.

The owned caller number is registered in ElevenLabs. Its dedicated secure Plivo outbound trunk is disabled and the imported number is unassigned; original Plivo application is unchanged. A local TLS1.3/OPTIONS probe returned200 Keepalive without a call. The India-host probe timed out; actual native SIP routing/recording/confirmation evidence is unqualified. The existing bridge is the deployed voice route. No cutover or new PSTN call occurred. All twelve calls remain used, no active call, zero office bookings; UK config/control stay false and the managed lease is free.


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


## Contextual purpose controls — 10 November 2026

Dynamic purpose interpretation now covers persistent targeted harassment/unrelated chat and clear automated answerers. Fresh original caller evidence and an actually played conditional warning protect genuine enquiries; callbacks, quotes, complaints, safety issues and identified arrangement requests take precedence over conflicting conduct labels. A server-controlled Valory/v4 Turbo goodbye precedes carrier hangup when audio succeeds; provider failure has a bounded fallback. Normal voice/turn settings and business consent remain unchanged. See [policy, edge cases and retained evaluation results](call-purpose-boundaries.md).

Runtime `87f35241103981826d49915d3c43c6c68afa402b` is deployed to the API and India gateway. 410 native backend tests passed in 58.18 seconds; 410 Linux/PostgreSQL17/Redis backend tests passed in 186.22 seconds. No new phone call: 20/20 attempts used, admission/UK campaigns off, both existing bookings preserved. Handset qualification and the prior confirmation-loop/unsaved-office-help findings remain open.
