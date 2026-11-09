# Fourteenth attended test result

9 November 2026. The owner explicitly requested one additional test call, capped at three minutes. It was placed exactly once. No automatic retry or further call is authorised.

The call ended without identity verification or a booking. ElevenLabs produced transcripts including “Yeah, I am” and “Please just tell me about it,” but all five carrier-observed transcript events lacked a verified original speech onset. The identity tool could not accept that evidence. It never reached account access, proposal preparation or booking confirmation. This is an input speech-timing verification failure, not a saved booking, a rejected booking assent or proof of caller refusal. Its precise detector cause still needs offline analysis.

The encrypted playback diagnostic was recovered. All six agent responses were complete, fully flushed and uninterrupted, with captured and received byte counts equal. No transport failure or pending playback remained; the close reason was closed. This call did not reproduce the earlier missing playback checkpoint. It does not qualify the booking path because identity failed first.

Authenticated Plivo metadata reports Callee hangup, Normal Hangup and a 100-second carrier duration. The application records 97 seconds. The protected stereo Ogg recording is 98.8465 seconds / 1,604,721 bytes; anonymous access 401 and authenticated access 200 were verified. Call identifiers, transcript, recording, diagnostic and carrier metadata remain private.

London API `0d1a941552d592759ad27a611686f976b0b3d2df` grants only the fourteenth attempt. Its parameter-only change passed four engineering tests, explicit 14-accepted/15-rejected settings validation, Ruff and whitespace checks. India voice runtime `61fd39fd496921144df7ad33e8751cf0daaf1a84` is unchanged from the 324-test playback repair. Provider configuration, office/worker services, the original Plivo number application and the disabled/unassigned SIP candidate are unchanged.

Calling is paused again. All 14 attempts are used, allowance 14, remaining 0, no active call and zero office bookings. No fifteenth call is authorised. The next independent investigation is an offline replay of the recorded caller channel through the original speech detector and timestamp association; do not weaken identity or consent evidence or ask the owner for another diagnostic call merely to capture existing audio.


## Speech detector cause confirmed — 9 November 2026

The previous 8 kHz detector found no caller speech in the saved call; the 16 kHz detector found five starts without lowering its threshold. The repaired bridge mapped all five to original carrier times, and the owned profile was corrected to the supplied full name. Voice runtime6b29593 is deployed and paused;326native/Linux tests pass. See [speech-detection investigation](call14-speech-detection-investigation.md) for exact evidence and limits. Fourteen attempts remain used, no further call is authorised, and fresh handset booking is still unqualified.
