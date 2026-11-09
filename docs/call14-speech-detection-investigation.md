# Why the owner's name was not accepted

9 November 2026. The owner reported saying their full name. The saved ElevenLabs transcript did not preserve that phrase: it contains an ellipsis at the first attempted reply and later “Yeah, I am.” This does not establish that the owner failed to say their name. All five caller transcripts lacked a verified original speech onset, so the identity tool could not access the account.

## Reproduced detector failure

The existing private stereo carrier recording was split into its caller and agent channels. The previous 8 kHz Silero detector found zero speech starts on the caller channel, despite recorded audio being present; its maximum speech probability was 0.366, below the unchanged 0.5 activation threshold. The agent channel produced 15 speech starts. An independent blind transcription also failed to recover the name accurately; it was not supplied the expected name as a hint.

The same caller waveform, resampled to 16 kHz for the 16 kHz detector, produced five starts and a maximum speech probability of 0.971. The threshold and minimum speech duration were unchanged. This isolates a model/input-rate sensitivity in the local detector rather than a missing caller name statement or a booking agreement phrase.

The repaired bridge now sends the identical 16 kHz PCM to both the local detector and hosted ASR. The original carrier-frame clock remains 8 kHz. Detector indices are converted back to that clock before the existing conservative onset calculation; transcript-arrival time never substitutes for original speech. Upsampling does not restore telephone bandwidth or itself prove better audible quality.

A replay through the actual repaired bridge found five speech starts and mapped all five to retained original frame times. New regressions cover 16 kHz-to-8 kHz index equivalence, missing original frames, identical detector/ASR audio and unchanged original timestamps. Both new regressions fail against the old module and pass against the repaired one. Private end-of-session diagnostics now include detector rate, detected starts and mapped starts to expose future timing failures.

## Full-name profile correction

The owned engineering customer profile stored only a given name. It has now been corrected to the owner's supplied full name, with an audit event; the private seed-name configuration was corrected too. The deployed existing identity parser accepts the owner's full-name statement against that corrected profile. This is a customer-data correction, not a hardcoded acceptance phrase or relaxation of the shared identity rules. Each phone conversation still receives its customer name dynamically from the backend.

The earlier name statement was absent from the native transcript and blocked by missing timing before this exact-name comparison could succeed. Therefore the stored given name is a separate corrected mismatch risk, not a proven alternative explanation for the old missing-speech evidence.

## Verified deployment and remaining limits

India voice `6b29593a9de93df99bc7ef85a4856731335ce831` is healthy with ElevenLabs selected and calling paused. London API `0d1a941552d592759ad27a611686f976b0b3d2df` is unchanged in source; its owned profile/private seed-name configuration were corrected and verified. The previous failed call still has identity false, no outcome and no booking. No failed result was rewritten.

The voice runtime passed 326 native tests in 49.83 seconds and 326 isolated Linux/PostgreSQL17 tests in 140.52 seconds. The targeted managed-phone suite passed 43 cases. Backend/script Ruff and whitespace checks pass. No frontend change or fresh build is claimed.

No additional phone call was placed. All 14 attempts remain used, allowance 14 / remaining 0, no active call, zero office bookings and UK controls off. A fresh handset identity/booking/latency check remains outstanding. The replay proves the local detector/onset repair; it does not establish that a fresh hosted transcript will spell every proper name correctly or that handset booking now succeeds. Native SIP remains disabled/unassigned and the recorded bridge remains selected.
