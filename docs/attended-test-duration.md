# Attended phone-test duration and latest results

10 November 2026. The owner explicitly removed the three-minute phone-test restriction. The new attended phone ceiling is 7200 seconds, ElevenLabs’ documented maximum. It is not an unlimited call. Normal closing, hang-up, stop requests and connection/inactivity handling still apply. No new call was placed for this change;20 attempts remain used with zero authorised additional attempts.

## Consistent call lifetime

Runtime 011e033f23615dcb8773765c93fd3f8916467150 is deployed on the London API/office and India gateway. Both protected status endpoints report 7200 seconds. The native ElevenLabs phone agent was patched and read back at 7200 seconds; its Valory voice, model, tools, knowledge, ASR, turn settings and platform controls were preserved. Automated isolated browser evaluations retain their separate 180-second ceiling.

A shared call_limits module now controls the API admission payload, gateway request validation, carrier time_limit, background-recording maxLength, managed bridge default and native phone configuration. The managed bridge no longer subtracts ringing/startup from the conversation timer. The office displays the duration reported by the API.

Phone tool capabilities, managed leases and engineering scoped credentials allow the extended lifetime with a five-minute operational grace. The short automated-evaluation expiry is unchanged. Only terminal engineering calls may have their managed lease reaped before a new session; release is fenced by the existing owner token. An in-progress call or another owner is preserved. Ended calls still cannot use business tools.

Carrier recording downloads and encrypted uploads remain bounded at 256MiB to accommodate longer stereo recordings. The codec and encryption are unchanged. Incoming history has a larger bounded phone allowance; the isolated evaluation limit remains unchanged. Existing per-turn consent freshness, proposal expiry, identity/privacy, suppression, one-call-at-a-time and attempt limits were not relaxed.

## Verification

384 backend tests passed locally in 108.65 seconds and on Linux/PostgreSQL17/Redis in 177.97 seconds. Twelve new tests cover carrier/native/recording duration consistency, tools after four minutes, engineering credentials beyond one hour, unchanged campaign expiry, denial after closure, terminal-lease cleanup and fencing, phone-capability TTLs and bounded long history. Ruff/whitespace passed. Four office tests and the Next production build passed.

A generated 20-minute stereo recording used the selected voice sample, not a person’s call. Its 38,400,044-byte carrier WAV exceeds the former 25MiB input bound, converted to 14,719,159-byte Opus/Ogg, decoded at 1200.0065 seconds and passed encrypted storage/read-back equality. Test storage was removed afterward. This is codec/storage evidence, not a two-hour PSTN endurance test or a human voice rating.

Live checks verified 7200-second status, gateway paused/healthy at011e033, office login 200, 20 retained phone attempts and no active call. No new server, number, plan, migration, password or secret rotation was required. UK campaigns and native SIP remain off. Existing appointments and recordings remain intact.

## Calls 19 and20, retained honestly

Call 19 used Valory, verified the first “Uh, yes, you are” without repeating the opening and ended normally without a playback failure. No booking was saved because the newly labelled fictional property’s deadline was 10 November while the first eligible gas diary window was 16 November. That was our test-setup mistake, not evidence of an unavailable real business diary. The office-help request was also not saved and remains a conversation-quality finding. The protected stereo recording is 84.6665 seconds/1,446,752 bytes with 401 anonymous/200 authorised access. The owner said Valory and interruptions were better, while reserving a final verdict.

Before the separately authorised call20, only that fictional obligation deadline was corrected to 30 November; 31 eligible gas windows were verified, and both existing bookings’ IDs/states/prices were unchanged. Call 20 verified identity, checked CP12 space and prepared a £75 proposal. The conversation repeated confirmation; the caller asked questions and later changed to combined service. The agent correctly searched combined availability. No confirm_booking tool call or saved booking followed. It reached the OLD initiation-based 180-second engineering timer at 179.75 seconds; answered time was 168 seconds and provider conversation 164 seconds. Its TimeoutError had no playback transport reason. The protected stereo recording is 167.5665 seconds/2,977,137 bytes with 401/200 verified. Do not call this a booking pass or attribute it to the previous playback failure.

The source also retains the preceding opening fix: completed speech before the first provider opening is separated from later replies using original frame timing and VAD ends. Actual call18 replay moves the first reply from 1.728 to 15.008 seconds, after the greeting, without changing acceptance phrases. Ongoing/overlapping early speech remains ineligible. Delayed clearedAudio receipts are handled independently of caller-media sequence numbers, with sent-clear and duplicate-receipt guards. These fixes passed 372 native and 372 Linux tests before this duration update. Broader talk-over/false-stop acoustic qualification and the repeated confirmation/office-follow-up findings remain open.

## References

- [ElevenLabs conversation flow and maximum duration](https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow)
- [Plivo call time_limit](https://www.plivo.com/docs/voice/api/call/make-a-call)
- [Plivo background recording](https://www.plivo.com/docs/voice/xml/record)
