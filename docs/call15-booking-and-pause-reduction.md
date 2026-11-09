# Fifteenth attended call and pause reduction

9 November 2026. **DONE_WITH_CONCERNS:** a real attended booking succeeded; the later pause changes are deployed and have controlled audio evidence, but have not yet had a fresh handset test.

## Actual phone result

The owner explicitly requested one call. It verified identity, offered real fixture diary space, read the selected arrangement and saved exactly one engineering booking after “Yes, please do it.” The appointment is a fictional test boiler service on Monday 16 November 2026, 8am–noon, £95 including VAT, payable to the engineer. It was not a reservation with a real customer or external business diary.

The carrier reports 117 seconds and Normal Hangup. ElevenLabs reports its native end_call tool ended the conversation. The protected stereo recording is 115.7465 seconds/2,020,881 bytes; anonymous access returned 401 and authorised access 200. App duration 98 seconds reflects the old business-finish step before the closing speech and is not the carrier duration. The owner said the call was smooth but pauses were too long. All previous calls and the saved booking remain intact.

Provider-reported time to reply audio after silence ranged from 3.020 to 5.333 seconds on this call. TTS first-byte time was approximately 78–93ms; the long gaps were not primarily voice synthesis. Business-tool durations included availability 1.935s, preparation 1.291s and booking 1.384s. A separate finish_conversation request before the spoken closing added another model/tool step.

The opening needed notice/identity recovery. The observer timestamp of the first reply precedes the completed greeting, while the native transcript places that reply later. This needs separate alignment analysis; it does not prove the caller answered early. Later full-name replies verified normally. No speech timestamp was moved or identity rule bypassed.

## Change and scope

Five backend/prompt/test files changed. Availability and preparation now request a brief, context-specific acknowledgement while the actual lookup runs. The agent may describe checking, but cannot announce availability or a saved booking before its successful result. Identity, booking confirmation, cancellation, follow-up and finish tools retain pre-tool speech off. End-of-turn thresholds, speculative generation, interruption configuration and all business-action guards are unchanged.

After the guarded phone commit succeeds, its result now includes close_with_native_end_call=true. The agent speaks a short truthful confirmation and uses native end_call directly. The existing authenticated carrier-end event finalises the call from saved database facts. It does not need an administrative finish_conversation round trip first. Non-phone evaluations retain their explicit finish contract. Caller speech cannot set this flag.

The one safety fact is that the new closing flag is returned only after the same guarded database commit succeeds. The regression uses real PostgreSQL booking rules, checks the phone record is still in progress after commit, and verifies an ended event finalises it as Booked without a model finish call. The non-phone test verifies it does not receive the phone flag. This is code/test evidence, reinforced by native synthetic closing runs; post-change handset evidence remains pending.

## Controlled audio measurements

These runs used real ElevenLabs generation with fictional client-tool results and fixed delays taken from call15. They did not call a phone or write to the CRM. They exclude telephone transport and speech recognition.

| Check | Baseline | Changed path | Interpretation |
|---|---:|---:|---|
| First speech during diary check |4.116s|1.243s|The changed speech truthfully acknowledged checking; it was not an availability answer or a booking claim. The lookup itself was still 1.935s. This reduces unexplained silence, not underlying service time.|
| Successful-booking closing, latest controlled batch |7.764s|3.807s and4.495s|Direct runs used zero finish_conversation requests. Small, variable sample; not a production latency estimate. Earlier baselines 3.591s/5.172s demonstrate variability.|

Forcing speech only around the finish tool was also explored (3.536s/3.729s with another baseline 5.172s); it did not consistently eliminate the gap and was not shipped. The shipped change removes the redundant step instead. All trials and initial harness failures are retained privately. The harness initially omitted the required is_error result field and later needed an explicit native-end handler; these were harness errors, not phone failures.

A real-provider replay through the actual managed Plivo audio bridge, with paced simulated carrier ACKs, completed both acknowledgements and the full booking readback: 437,120 μlaw bytes, with no transport failure. It used a separately isolated evaluation session and saved no main-diary booking. This clears the previously fragile combined-caption/audio path for the tested sequence, not every real interruption case.

## Verification

Two regression assertions failed on the prior runtime and passed after the fix. Full native suite: **355 passed in 90.95s**. Exact committed-source Linux/PostgreSQL17/Redis suite: **355 passed in 171.65s**. Ruff and whitespace checks pass. No frontend source/build change.

Provider tests: **17/18 phone-profile and 3/3 browser-profile judgments passed**. All tool-selection/generated-proposal checks passed. The one failed technical-recovery judgment claimed that offering an optional callback was actually recording one. Its generated response made an offer, called no tools and claimed no callback was saved; the test's unchanged success condition explicitly allows an optional offer. The other repetition passed. The failed result is retained, was not rerun away, and the criteria were not loosened. Treat the aggregate as 20/21 raw judgments, not an all-green native suite.

The API at 4330a3643e11dfa6c1161ff510602a93fd3a747c is deployed healthy. India transport remains 56c5e43799d40d56abf28427a989c030b71f7f4e; the owned ElevenLabs phone/browser configurations were updated and read back. Office and worker/Beat are unchanged. Public readiness/access checks passed, including protected recording. All 15 attempts are used, limit 15, remaining 0, no active call, gateway admission off, UK config and database controls off, and the managed evaluation lease free. The one engineering booking remains saved. No sixteenth call is authorised or placed. Only the temporary client-tool benchmark agent created by this investigation was deleted; existing owned agents and evidence were preserved.

## Debug report

- Symptom: smooth conversation and successful booking, with long silent pauses.
- Root cause: latency-adaptive automatic tool speech stayed silent during lookup steps, plus an unnecessary model/finish-tool step before the final confirmation. Measured synthesis startup was fast.
- Fix: managed/agent.py:34 forces truthful speech for the two lookup/proposal tools; managed/phone.py:152 returns the success-only phone closing flag; managed/prompt.txt:19 consumes that flag. Test coverage is in test_managed_phone.py:81 and:419 plus the non-phone candidate test.
- Evidence: before/after regression failures and passes, 355 native/Linux tests, controlled real-provider audio and full bridge replay, live configuration/access/data-preservation checks.
- Related: prior account-return coalescing removed another serial model step; original speech/playback guards must not be weakened to hide latency. The opening timestamp association remains a separate concern.
- Status: **DONE_WITH_CONCERNS**. Updated handset pauses, full cancellation/interruptions/safety scenarios, independent voice/conversation ratings, UK routing and broader production gates remain unqualified. Do not infer human equivalence or general production readiness from this one successful engineering booking.
