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
