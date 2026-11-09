# Thirteenth attended call and playback repair

9 November 2026. Engineering investigation; handset booking remains unqualified. No further call is authorised.

## Observed call

The owner explicitly authorised one thirteenth call capped at 180 seconds. London API `02d0e02` granted only that additional attempt; India used `d84ff58`. The call passed identity, account lookup, service discussion, slot selection and proposal preparation. The owner said “Yeah, please do it.” The booking tool correctly reported `caller_agreed=true` but returned `readback_incomplete`. No completed readback event was stored and no office booking was saved. The exact provider-declared readback passes the current substantive matcher, so this failure was not another unsupported yes phrase or the earlier postcode/year defect.

The owner confirmed the service disconnected. Authenticated Plivo CDR reports API Request, Normal Hangup, 97 seconds. ElevenLabs reports client disconnected 1000. These prove a service-side termination but do not preserve the precise internal transport trigger. Do not attribute it to caller hangup or claim that the exact trigger was recovered.

The protected stereo recording is available: 96.3065 seconds, 1,729,095 bytes. Anonymous access returned 401; authenticated access returned 200 and decoded as two-channel Ogg. The recording, transcript, provider details and failed outcome stay private. The main database retains 13 engineering attempts and zero bookings; UK campaigns and phone admission remain off.

## Reproduced code defects

A deterministic interleaving holds the resampler's final write on carrier credit while a new native speech segment arrives under the same caller event. On the previous code the new audio loses its final checkpoint. The same code also copied mutable captions after that await, allowing a queued answer to change an earlier segment's proof. This is a confirmed implementation defect consistent with the missing evidence; the past call's raw playback state was not retained, so it is not established as the sole trigger of attempt 13.

The repair counts PCM actually captured, freezes segment text/alignment/completeness before awaiting the resampler tail, and marks a turn fully flushed only if no later received bytes remain. Every subsequently consumed packet makes its physical segment eligible for its own final checkpoint. Interruption still invalidates completion. The new regression fails before the repair and passes after it, without a telephone call.

A second deterministic check proves that transport failure could complete an input/watcher task without being raised by the managed runner. That path appeared to be a normal finish and cancelled pending audit writes. The runner now raises the transport's failure reason and drains queued interrupted-playback evidence before cancellation. A normal remote close remains distinguishable from a failed transport.

Private diagnostics now retain at most 32 caption/alignment states, 8,000 characters per text field, byte counts and transport close/failure reason. They contain no PCM, API key or session capability, are encrypted with the existing state key and expire after 24 hours. Diagnostic-store failure cannot mask the primary exception. This information is not a public log or source artifact.

## Verification and limits

The repaired source is `61fd39fd496921144df7ad33e8751cf0daaf1a84`. Native backend 324 tests pass in 48.84 seconds; 324 isolated Linux/PostgreSQL17 tests pass in 138.61 seconds. Backend/script Ruff and whitespace checks pass. New checks cover the forced flush interleaving, frozen earlier proof, normal versus failed transport close, retained interruption evidence, encrypted bounded diagnostics and an unavailable diagnostic store.

A real ElevenLabs replay used the matching Albert Road/Southsea fixture and forced pre-tool acknowledgements with simulated paced carrier acknowledgements. It completed identity, service discussion, availability and the full address/postcode/date/window/price readback. It did not commit a booking, dial a handset or measure human voice quality. Existing original speech timing, completed playback, identity, semantic intent, capacity and idempotency checks remain enforced.

First identity confirmation was rejected as notice_incomplete before the completed opening evidence; a later confirmation passed. Original-onset mapping for untranscribed early speech and real interruption/latency behavior remain qualification work. Do not retimestamp an early reply, relax a consent guard or invent a saved booking to obtain a pass.

Calling remains paused with 13 of 13 attempts used. The direct SIP candidate remains disabled and unassigned; the recorded bridge remains selected. Fresh attended booking and disconnect verification, the UK route and the other production gates remain outstanding.


## Deployed verification

India gateway `61fd39fd496921144df7ad33e8751cf0daaf1a84` is healthy with ElevenLabs selected and admission false. London API remains `02d0e0256bf2fa8bfbd2e590adb86375cdbdbf9c`; office and worker/Beat are unchanged. Authenticated preservation checks found 13 retained engineering calls, zero bookings, no active call and a free managed lease; UK configuration and campaign control are false. The allowance is 13 used / 13 limit / 0 remaining. Anonymous tool/session access is denied and office access redirects to login.

A synthetic roundtrip on the deployed India host verified the existing encryption key, actual Redis connection and 24-hour diagnostic TTL; that temporary key was deleted. It did not contact a voice provider or telephone destination. Earlier regression and provider replay evidence remains private and preserved. No call 14 is authorised. The precise trigger of the old call 13 disconnect remains unproven; fresh handset booking and termination qualification are still required.
