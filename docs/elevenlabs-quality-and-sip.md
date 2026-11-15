# ElevenLabs quality tuning and SIP preparation

8 November 2026. Engineering release; DONE_WITH_CONCERNS. No new PSTN call, host, number rental, subscription or staff reset. All twelve attended calls remain used; no thirteenth is authorised.

## Deployed conversation configuration

Both owned ElevenLabs agents retain Lily/v4 Turbo, Scribe Realtime, GPT-4.1, prompt-context business facts, seven authoritative business tools and native end_call. Each now has nine attached native regression tests, six transcript-based evaluation criteria, eight domain-recognition terms and a three-entry pronunciation dictionary (CP12, VAT, Southsea). These resources are real provider objects, provisioned idempotently from versioned source and private resource state.

Availability lookup and proposal preparation use latency-aware pre-tool speech. Identity, booking commit, cancellation, follow-up recording and finish remain off: extra speech can change the question/readback evidence or make an action sound saved before it is. Acknowledgements must state only that a check is underway; they cannot claim business success. Silence fillers remain disabled. This is selective conversation design, not a requirement to fill every pause.

The selected balanced phone profile retains normal eagerness and speculative generation off. A more eager/speculative candidate was compared using actual provider audio with a synthetic caller and simulated paced carrier acknowledgements. The split identity reply included a 700ms internal pause. Both candidate probes waited until input completion. Their measured input-end-to-first-reply-audio values were2.535s (balanced) and2.134s (fast). One pair is neither a causal speedup estimate nor a latency distribution, so the faster candidate was restored to balanced pending broader acoustic qualification.

Pure nonverbal acknowledgement filtering is configured for the browser candidate only. The phone filter was tested and left off: an ignored hum could leave an old local VAD onset attached to the next ASR reply. Main phone identity would correctly reject that original timing; the isolated browser-style evaluation did not prove a phone pass. Never remove timing guards just to make an acknowledgement filter pass. Words such as yes, no, stop and cancel are never added to the ignore list.

## Original speech evidence repair

A second discovered issue was split provider ASR: one original caller turn could produce multiple final transcript fragments. The old observer cleared the entire onset queue at the first fragment and reported the second without verified timing. The deployed observer now keeps the earliest original onset within that user turn, clears the carried onset when an agent response begins, and rejects late prior event IDs without consuming new speech. It never replaces onset with transcript-arrival time. Unit tests cover fragmentation, duplicate delivery, late prior events and missing fresh speech. An actual provider probe recovered both fragments with original timing after completed simulated playback and returned the correct service. This is not handset booking qualification.

## Native regression evidence and interoperability

The suite covers actual owner phrasing, natural/frustrated agreement, cancellation, negated cancellation, changed date, withdrawal, cancellation questions and honest recovery after an unavailable booking. Test contexts are synthetic prior conversation/tool results. Unit runs assess provider behavior; no authorised live CRM session is supplied, so unit-tool executions cannot create an office booking. Actual database booking/cancellation was independently verified in the preceding release.

The final exact provider configuration passed18/18 phone-agent runs (nine cases repeated twice) and3/3 browser-agent checks. Earlier baseline18/18 and intermediate tuned18/18 results are retained. Failed parameter-binding pilots, a cancelled mismatched batch, an intermediate repeat-write failure, and stale-tool-reference failures also remain retained. No failure is relabelled a pass.

Native parameter assertions did not resolve the nested proposal field using three attempted path forms. The current native tests verify tool identity; the versioned runner additionally parses every generated request and strictly checks its proposal ID. A native UI green result alone is not the full parameter check. The runner exits unsuccessfully if either native or strict checks fail. A changed inline tool description can create a new provider tool ID; the resource provisioner refreshes test references, and the runner rejects stale references before submitting a paid invocation. Authorization/session failures explicitly forbid another booking write or request for another yes. An evidence_pending result permits one bounded retry only.

Six native criteria evaluate truthful saved outcomes, contextual consent, bounded recovery, identity/privacy, cancellation/stop handling and concise wording. Transcript evaluation cannot judge actual audible quality, handset interruptions or MOS. Independent listening and the full held-out case matrix remain required.

## Existing-call performance evidence

Authenticated provider metrics from the failed twelfth owner call reported TTS first-byte median0.067s across8 speech responses and first-audio-since-silence median2.207s across8 responses. LLM first-byte median was0.612s across14 generations; silence-before-initiation median0.304s across8 responses. These are vendor stage measurements from one call, not handset percentiles or independent participant samples. They support investigating model/tool roundtrips rather than treating voice synthesis alone as the cause of pauses. The added independent booking-intent classifier still adds a processing step and needs timing qualification.

## UK Twilio SIP comparison

A separate secure Twilio outbound trunk and an unassigned ElevenLabs SIP entry were staged for the existing UK caller ID. The trunk has no mapped authentication list, associated number or inbound routes. The existing number configuration was verified after staging. The UK media relay remains the working call route and customer campaign dialling remains paused.

Certificate-verified TLS probes from the London app host timed out on the default, Dublin and Frankfurt Twilio termination addresses. These probes establish no call and do not measure connectivity from the ElevenLabs SIP edge. SIP audio and speed improvements remain unmeasured.

For the first comparison, use the same consenting handset, agent voice and script on both routes. Measure answer to greeting, end of caller speech to first audible reply, and time to yield on an interruption. Compare equivalent scripted turns with and without CRM work separately. Before enabling SIP booking, verify equivalent call-bound identity, recording, current caller authorisation and completed playback evidence, then confirm CRM booking and opt-out behaviour. Use an isolated test profile for audio-only qualification.

## UK agent-to-agent telephone QA

Use **Brightwater QA — UK synthetic customer receiver** on the dedicated Twilio test line. The receiver plays the fictional Peter Lund role, has no CRM or outgoing-call tools, and has a 145-second limit. Assign it to the test line only for a supervised run. In Brightwater **Call controls → UK test call**, select Peter Lund and use the dedicated owned test destination. After the call, unassign the receiver and review the CRM outcome, diary entry, recording and both ElevenLabs conversation traces.

The first run connected both agents over Twilio, verified identity, looked up slots and prepared a booking. The receiver transcribed the spoken door number fourteen as forty and asked for a correction. The call reached the receiver's time limit before agreement, and no appointment was saved. The CRM classified the attempt as **No answer** even though Twilio recorded a connected conversation. [First call record](https://office.46.101.11.137.sslip.io/calls/b002e40c-c1f4-4b96-8ee0-5cd70c0598ed)

On the second call, the receiver understood the address and asked Alex to book. The CRM rejected Alex's readback as incomplete and saved no appointment. Alex re-read the details and the receiver ended the call before a further confirmation. Twilio recorded 110 seconds and the protected recording decoded to 104.4 seconds. The receiver was unassigned after both runs. [Second call record](https://office.46.101.11.137.sslip.io/calls/50ed7b90-8dc8-456d-ba03-528097ae6c36)

These are repeatable synthetic carrier tests with real audio and CRM effects. Use the fictional diary and keep customer dialling paused. Both numbers are managed by Twilio, so this setup measures that route, without a mobile handset, mobile radio conditions or human response behaviour. Direct SIP qualification uses a separate media path.

### 16 November regression run

Alex now reads the prepared wording from the CRM, including the visit year and arrival window. The carrier-backed confirmation rules still require a completed readback and a fresh reply.

| Scenario | Observed result |
| --- | --- |
| Homeowner booking | One £95 booking saved after one confirmation. The recording is available. [Call record](https://office.46.101.11.137.sslip.io/calls/a58517d8-432d-4533-a367-37883585bbdf) |
| Human callback | The CRM saved **Callback requested**. The recording is available. [Call record](https://office.46.101.11.137.sslip.io/calls/5eaef052-91b9-431b-aaf8-aef248821e3c) |
| Gas smell | The CRM saved **Gas emergency advice**, and completed playback included the emergency number. [Call record](https://office.46.101.11.137.sslip.io/calls/6b69bdec-b321-4bd2-b8fd-4cad67899e9a) |
| Proxy answer | No account details were disclosed. The caller said Joan was unavailable and also asked why Alex was calling. The classifier missed **Not available**. The revised classifier returned the correct outcome in replay; a fresh telephone retest is pending. [Call record](https://office.46.101.11.137.sslip.io/calls/6f3666c5-7389-44ce-a51c-7aeb2dd78940) |
| Voicemail detection and three-property landlord | Twilio recorded zero connected audio seconds for each. ElevenLabs logged receiver initialisation failures and the workspace reported zero credits remaining. Both scenarios still need a new call. Full voicemail delivery also needs an approved callback number and a mailbox check. |
| Direct SIP | The planned audio-only call was cancelled before dialling when the provider reported zero credits. |
| Permanent opt-out | Covered by the backend regression suite and the earlier India suppression record. A fresh live opt-out on the reusable UK test number would suppress that number. The spoken acknowledgement still needs a live test with an isolated or disposable destination. |

517 backend tests passed after the proxy change. Twelve native ElevenLabs checks passed before credits ran out. The receiver was unassigned after testing. The normal attended daily limit was restored to six and automatic customer calling remained paused.

### Creator-plan retests

The upgraded workspace was verified with 121,000 available credits before testing. The earlier credit-blocked tests were resumed on the two owned Twilio lines.

| Scenario | Saved outcome |
| --- | --- |
| Proxy answer | **Not available**. The transcript contains the opening identity question and no account disclosure. [Call record](https://office.46.101.11.137.sslip.io/calls/15c9b5ed-4b04-4c16-a5e7-2796887ae212) |
| Synthetic voicemail greeting | **Voicemail**. The CRM recorded the detection. Full mailbox delivery remains open pending a real approved callback number and receiving mailbox. [Call record](https://office.46.101.11.137.sslip.io/calls/fc0a7d1b-7cc9-4c43-a138-cc70624c3e4c) |
| Multi-property landlord | **Booked**. One £180 booking with three confirmed gas safety visits after one consent turn. The protected recording decoded to 218.5 seconds. [Call record](https://office.46.101.11.137.sslip.io/calls/b7fc415a-cd4c-4f4e-b224-70e152ca9d62) |

### Direct SIP call

The first audio-only probe reached Twilio termination. ElevenLabs then rejected the receiving agent at its daily limit. A second probe with a temporarily higher receiver limit completed **28 seconds of two-way audio**. ElevenLabs recorded both scripted receiver answers, and Twilio showed completed SIP termination and inbound legs. This verifies the direct route can carry an agent-to-agent call. Its effect on end-to-end speed and the CRM booking and recording safeguards still needs a controlled comparison.

The original receiver limit was restored, the receiver was unassigned, and the temporary SIP credential mapping was removed. Automatic customer calling remains paused.

### Model comparison

Six native behaviour cases per model checked consent, date changes, engineer questions, voicemail, emergency handling and a three-property readback. All three models passed the six checks using Brightwater's full agent instructions and tools. A partial-override run omitted the tools and was excluded.

| Model | Behaviour checks | Median text-to-first-audio |
| --- | ---: | ---: |
| GPT-4.1 | 6/6 | 0.957 s |
| Gemini 3.5 Flash-Lite | 6/6 | 0.975 s |
| GPT-6 Luna | 6/6 | 1.233 s |

The speed probe used three synthetic text turns per model, the same Eleven v4 Turbo voice configuration and an authenticated WebSocket with no diary tools. It excludes speech recognition, handset delivery and CRM time. GPT-4.1 remains the deployed model. The small difference between GPT-4.1 and Flash-Lite does not establish a reliable speed advantage for either.

## Direct Plivo SIP: prepared, not activated

The existing owned Plivo number is now registered in ElevenLabs as a SIP number. A new dedicated outbound Plivo trunk uses dedicated digest credentials, secure signaling/media and explicit PCMU/8000 + PCMA/8000 codecs. The trunk is disabled, no agent is assigned to the imported number, the Plivo number's original application is unchanged, and the production application still uses its working recorded India bridge. Nothing was ported or purchased.

Authenticated account reads verified the exact owned trunk and caller number. Plivo's individual/unfiltered trunk reads returned502 during preparation; a filtered authenticated listing returned the exact trunk and credential binding, so the source uses that checked fallback rather than guessing a hostname. One rejected import was reconciled against zero imported numbers before correcting codec enum formatting. Mutations are durably marked; uncertain requests are never automatically repeated.

A local certificate-verified TLS1.3 connection to the verified trunk domain completed, and a non-call SIP OPTIONS probe returned200 Keepalive. No INVITE, PSTN destination or phone call was sent. The probe from the India host timed out; neither result proves connectivity from ElevenLabs' own SIP/media edge or caller-ID/India routing. Standard SIP import was accepted on the existing Starter account. India-isolated workspaces and static-IP options have separate Enterprise provisioning; generic SIP must not be incorrectly described as Enterprise-only. No upgrade occurred.

Cutover gates remain: authenticated provider-to-carrier signaling/media and allowed route/caller ID; lifecycle and hangup mapping; provider recording copied into protected encrypted CRM storage; call-bound session/context and tool authentication; and an equivalent validated original-speech/completed-playback confirmation contract. Plivo Zentrunk does not provide the existing Voice API recording path. Current bridge evidence cannot be asserted on native SIP without replacement. Never assign/enable this route for booking merely because import or OPTIONS succeeded.

## Reproduce safely

Supply the provider key only through the private environment. Keep all state/output paths outside this source package. Provision the agent config, provision/refresh native resources against its actual tool IDs, and reapply configuration with the quality state to attach resources. Refresh native references after changing tool definitions.

```sh
PYTHONPATH=backend/src python scripts/provision-managed-quality.py --state /private/quality.json --agent-state /private/phone-agent.json
PYTHONPATH=backend/src python scripts/provision-managed-agent.py --state /private/phone-agent.json --api-url https://your-api-host --phone --quality-state /private/quality.json --profile balanced
PYTHONPATH=backend/src python scripts/provision-managed-quality.py --state /private/quality.json --agent-state /private/phone-agent.json
PYTHONPATH=backend/src python scripts/run-managed-native-tests.py --agent-state /private/phone-agent.json --quality-state /private/quality.json --output /private/unique-invocation.json --repeat 2
```

The test runner retains the invocation before polling and refuses to reuse an output path. Resolve an uncertain submission using its retained invocation/name; do not submit another batch blindly. Native test contexts are not handset or real business success evidence.

`prepare-managed-sip.py` creates only dedicated inactive resources and verifies the existing application. `check-managed-sip-transport.py` performs a bounded TLS/OPTIONS check with no call establishment. Neither command enables a trunk, assigns an agent, dials a phone, grants another attended attempt or qualifies booking writes. Private SIP credentials must never enter a source archive.

Primary references checked: [ElevenLabs testing](https://elevenlabs.io/docs/eleven-agents/customization/agent-testing), [Plivo integration](https://elevenlabs.io/docs/eleven-agents/phone-numbers/telephony/plivo), [SIP specification](https://elevenlabs.io/docs/eleven-agents/phone-numbers/sip-trunking), [Plivo technical specifications](https://www.plivo.com/docs/sip-trunking/concepts/technical-specifications), [official API schema](https://api.elevenlabs.io/openapi.json).


## Audio protocol regression and final runtime repair

A final real-provider probe forced acknowledgements before both read-only tools. Initial and intermediate attempts exposed more than text tests could: trailing PCM packets have empty captions, pre-tool speech shares a caller event ID with its answer, and answer audio can precede its text event. The first observer could reset completion on a trailing packet; an intermediate separate-response approach misplaced the answer's opening audio. Both failures are retained privately and were not called passes.

The final observer accumulates the provider's declared and aligned speech within the caller turn, deduplicating declared response IDs. It streams PCM immediately, waits a200ms stream-settling interval only before the final checkpoint, and freezes each physical playback proof before carrier acknowledgement. New audio/text cannot rewrite an already-pending proof. Only complete aligned speech with an uninterrupted carrier checkpoint can supply completed evidence. Missing or interrupted speech stays ineligible. The next utterance retains its original caller onset; no transcript-arrival timestamp replaces it.

The final forced-acknowledgement probe used real ElevenLabs audio and real isolated business-tool requests with simulated paced Plivo acknowledgements. Identity, the outbound reason, availability and the full property/service/date/window/price booking readback completed; no booking commit or physical phone call was made. This checks protocol behavior, not handset audio or conversational ratings. Tests cover text arriving before and after audio, empty-caption trailing PCM, multiple physical segments under one caller event, frozen earlier proofs and interruption behavior.

Runtime source d84ff58 passed319 native tests in79.90s and319 isolated Linux/PostgreSQL17 tests in130.39s. Final backend/script lint also passes; the package sorts two existing migration imports without changing behavior. India alone receives this runtime update. London API, office and worker releases are preserved. The gateway remains on ElevenLabs with admission disabled. No thirteenth call is authorised.


## Attempt13 playback investigation — 9 November 2026

The thirteenth attended call failed to save a booking despite recognised agreement and was disconnected by the service. A reproducible playback-flush race and silently completed transport-failure path are repaired in61fd39f; the precise past trigger was not retained. See [call13-playback-investigation.md](call13-playback-investigation.md) for actual carrier/recording evidence, before/after regression and deployment.13of13attempts are used, no further call is authorised and calling remains paused. Earlier provider tests and synthetic audio checks remain engineering evidence; they do not qualify handset booking.
