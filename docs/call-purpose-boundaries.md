# Contextual call-purpose boundaries

The attended ElevenLabs/Plivo candidate now distinguishes deliberate misuse and automated answerers from genuine customer enquiries. These controls are an engineering candidate; handset behaviour and end-to-end latency still need an attended test. No further call is authorised by this change. All 20 attempts remain used; admission and UK campaigns stay off.

## Decisions and enforcement

The existing server-owned GPT-4.1 turn interpretation now also classifies current purpose: ordinary conversation, unrelated chat, targeted harassment, automated menu/answering assistant or voicemail. It reads the entire current reply in context. There is no list of caller acceptance, abusive or IVR phrases to match. Existing identity, opt-out, recording-refusal and speaker-change decisions are retained.

A first unrelated/targeted-harassment request goes through the existing finish tool, which refuses to end and instructs one short conditional warning and a return to the Brightwater enquiry. Termination requires two distinct consecutive misuse turns for targeted harassment, or three for unrelated chat, with an actually completed, uninterrupted warning between earlier misuse and the latest turn. A valid enquiry, unknown intervening turn or conflicting interpretation breaks that streak. Model/tool retries cannot count as new caller turns. These numerical policy thresholds are deterministic safeguards around dynamic language interpretation.

A clear current automated menu, automated answering/call-screening assistant or voicemail can end without a warning. The decision still requires a fresh, originally timed, trusted carrier observer turn. A human receptionist, proxy, assistive speech device, accent, quoted menu, isolated tones/music or silence cannot establish automation. Uncertainty prompts clarification rather than a conduct warning. No keypad navigation, account-detail voicemail or conversation with another bot is allowed.

The pre-existing interpretation prefetch enforces the decision independently of the conversational agent choosing its end tool. A fresh-context check and database transaction preserve the decision and finalise from existing saved facts. No conduct ending creates a contact suppression, cancellation or inferred callback. An earlier saved booking remains saved.

The authenticated gateway resolves the active call entirely from server-owned state, stops the native ElevenLabs session, drains incoming caller audio and plays one neutral goodbye using the owned phone agent's current voice/model. Carrier playback receipts gate completion. This operational audio is never identity/readback or customer-consent evidence. Only the exceptional closing path makes an additional agent-profile/TTS request. It is bounded; provider/connection failure falls back to hanging up, so an audible goodbye cannot be guaranteed on a failed line. Ordinary booking closing and its playback proofs are unchanged.

## Protecting real conversations

| Situation | Handling |
| --- | --- |
| Swearing about a failed booking, angry price objection, repeated genuine agreement | Continue the service flow; not harassment |
| Complaint, refund query, report quoting abuse, urgent problem | Preserve enquiry; no conduct warning or misuse termination |
| Gas/CO danger, symptoms or distress | Safety/help response takes precedence; no punitive ending |
| Related repairs, extra services, changed dates, cancellation, landlord/tenant questions | Existing business tools and authority checks; no unrelated-chat classification |
| Brief friendly aside with a service request | Continue normally |
| Hearing/language/accessibility needs or unclear ASR | Clarify patiently; no voice-based automation inference |
| Targeted sexual/personal remarks with no genuine enquiry | Warn first; persistent misuse can end politely |
| Unrelated entertainment, repeated roleplay or deliberate repetition to consume resources | Short boundary warning; persistent diversion can end politely |
| Return to a real enquiry after a warning | Reset the misuse streak and resume |
| IVR options, unequivocal voicemail or automated answering agent | End without account disclosure or menu navigation |
| Human quoting an IVR, receptionist offering a transfer, human using AI software | Continue subject to existing identity/privacy checks |
| Wrong number, recording refusal, contact opt-out or changed speaker | Existing independent privacy/suppression controls take precedence |
| Interrupted warning, fabricated quote, old interpretation or newer caller reply | No misuse termination on that evidence |
| Tool/provider failure or repeated booking readback rejection | Existing bounded retries and truthful recovery; never blame caller wording |
| Prompt injection, invented tool results, requests to dial someone else | Treat as untrusted content; existing scoped tools/auth remain authoritative |
| Saved booking followed by an abusive turn | Preserve booking and price; ending a call does not cancel it |
| Caller hangs up or transport fails during goodbye | End/reconcile existing call; no redial or fabricated playback success |

The existing 20-second native silence setting, bounded output/audio queues, per-tool retry limits and 120-minute attended outer guard remain. Interpretation request budget now uses fixed five-minute buckets, preventing the earlier cumulative 128-request limit from disabling checks during a legitimate long call. Classification failure does not authorise business changes or create a misuse-ending decision.

## Flow and quality boundaries

Valory, v4 Turbo, Scribe Realtime, normal turn eagerness, speculative-generation setting, interruption filtering and existing business tool IDs are preserved. Routine enquiries get no additional interpretation API round trip; the additional fields share the existing request/cache. Added instructions do increase prompt size. No claim is made that handset latency is unchanged without measurement. End-to-end timing and interruptions need fresh phone qualification.

This work does not repair or conceal the call20 repeated-confirmation problem or call19 unsaved office-arrangement request. The two existing bookings, all failed call records and recordings remain retained. Direct SIP is still disabled/unassigned. UK customer routing and production qualification remain open.

## Research basis

ElevenLabs documents native [end_call](https://elevenlabs.io/docs/eleven-agents/customization/tools/system-tools/end-call) conditions and an optional farewell, and [voicemail detection](https://elevenlabs.io/docs/eleven-agents/customization/tools/system-tools/voicemail-detection) based on conversational patterns. This implementation uses the existing guarded finish/end path so that independent context, warning and business-state checks stay in force; an additional autonomous voicemail tool is not enabled to bypass those guards.

Plivo's [outbound call API](https://www.plivo.com/docs/voice/api/call/make-a-call) offers machine detection with a documented 2–10 second detection window and a direct-hangup mode. That mode is not enabled here: contextual checks and conservative uncertainty handling better fit the priority of protecting human enquiries, without adding a carrier detection wait to every answered call. This is an implementation choice, not a measured claim about carrier detector accuracy.

Remaining qualification includes actual IVR/voicemail/carrier audio, long or noisy automated greetings, multilingual menus, screening systems that hand off to a human, hold/fax/no-speech handling, sustained adversarial prompting, distress scenarios, independent ratings and end-to-end false-positive/latency measurements. No system can guarantee correct handling of every possible conversation.


## Verification and deployed scope — 10 November 2026

The final runtime is `87f35241103981826d49915d3c43c6c68afa402b`. London API and India gateway are updated; office remains `011e033f23615dcb8773765c93fd3f8916467150`, worker/Beat remain unchanged. No migrations, customer imports, diary resets, resource purchases, SIP activation or phone attempts are part of this release.

- Backend: 410 native backend tests passed in 58.18 seconds; isolated Linux/PostgreSQL17/Redis: 410 Linux/PostgreSQL17/Redis backend tests passed in 186.22 seconds. Ruff and whitespace checks pass. The office source is unchanged, so its prior four tests and production build are retained rather than claimed as rerun.
- Real GPT-4.1 contextual classification: the expanded 38-case matrix returned 37 available, correct classifications and one unavailable gas-enquiry interpretation; the interpreter did not retain the underlying error category. Its existing request timeout is four seconds. Unavailability creates no misuse-ending decision. The native emergency response remains instructed to give advice before tools. The initial 30-case run had one overly strict expected label: a human fetching Helen correctly triggered nonterminal speaker-change privacy handling. Raw results are retained.
- Current conversational prompt/tool selection: 13/13 synthetic real-model cases passed, including natural/frustrated booking, cancellation, service change, first misuse, repeated harassment, automation and return to service. Separate real-model checks confirmed both required conditional warnings after a guarded `finished=false` result. An earlier prompt merely redirected without warning; it was corrected and the earlier evidence is retained.
- Native ElevenLabs: the initial full 15-case invocation recorded 13 passed and two failures because its test condition rejected the intended `finish_conversation` plus `end_call` sequence as two calls. The evaluator now requires guarded finish first, exactly one finish, at most one native end and no other business operation. The six corrected boundary cases passed 6/6; the nine unchanged booking/recovery cases passed in the earlier same-profile invocation. All 15 current cases therefore have passing evidence, across those two invocations. These simulations lack a live phone capability and do not execute real business webhooks or qualify their CRM outcome.
- Offline replay of all nine actual call20 caller turns: one sexual diversion classified as harassment; all eight other turns, including the subsequent combined-service enquiry, remained ordinary service conversation. Original native history was used only as test data, never promoted into new caller-consent/playback evidence. No new carrier call, audio replay or business write occurred.
- Real ElevenLabs current-phone-profile lookup and Valory/v4 Turbo farewell generation produced 3.6 seconds of PCM in 1.75 seconds into a counting sink. This verifies provider generation, not audible handset delivery. Transport regressions separately use the real bridge/codec/checkpoint implementation with simulated carrier receipts, including draining 150 incoming media frames during the closing and provider failure handling.
- Live verification: API/gateway health, protected dashboard release, ordinary UK controls off, native backend selected, gateway admission off, 20/20 attempts used and no active call. Unsigned endpoints are denied; authenticated stop of a nonexistent call returns404 without a carrier operation. Database counts and both confirmed booking IDs/states/prices match before and after. No suppression or followup was added.
- Read-back, identity and consent gates are retained. A conflicting followup or identified arrangement request takes priority over a conduct label. Ordinary turns do not perform the warning-playback lookup when no warning quote exists.

Native phone/browser profiles were compared before/after: only the prompt/end-tool description and native test attachments changed. The selected voice/model, ASR, turn eagerness, speculation, interruption filters, business-tool IDs, knowledge base, auth and recording controls were preserved. Direct SIP remains disabled/unassigned; no new host or subscription was created. Fresh attended handset testing is still required for real automation detection, warning/return-to-service behaviour, polite closing audibility and full latency/interruption quality.
