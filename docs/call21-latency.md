# Call 21: response-latency investigation

The latest owner-initiated engineering call saved a £75 CP12 appointment and ended normally. The owner reported a slow opening and slow replies. There are now 21 retained engineering attempts and three saved fictional bookings. No additional telephone call was placed during this investigation.

## Recorded baseline

| Stage | Evidence | Measurement |
| --- | --- | --- |
| Ringing | Account-authenticated Plivo call record | About 8 seconds before answer |
| Answer to first managed opening marker | Carrier answer time and authenticated gateway event | About 6.3 seconds; this is not a separately measured handset first-audio timestamp |
| Provider first opening audio | ElevenLabs conversation metrics | 0.076 seconds after provider initiation; excludes connection preparation |
| Voice first-byte generation | ElevenLabs TTS metrics | About 0.066–0.080 seconds |
| Native model first token | ElevenLabs per-turn metrics | About 0.45–0.94 seconds |
| Business webhook | ElevenLabs tool metrics | 1.22–2.58 seconds |
| Closing response after silence | ElevenLabs `convai_ttf_audio_since_silence` | 3.455 seconds |

The provider voice generator is fast. Serial connection preparation, model/tool round trips and excessive readback wording account for substantial waiting outside it. Ringing time is distinct from silence after the person answers.

## Changes

1. After the sole carrier initiation is acknowledged, a best-effort background task prepares the provider URL while the phone rings. The capability is encrypted, call/agent-bound, expires after 45 seconds and is consumed once. The normal active-call, destination, runtime and scoped-session checks still run before use. Failed/missing preparation falls back to the existing route; it never initiates or retries a telephone call.
2. Authenticated agent captions can warm text-keyed readback analysis while audio plays. A caption does not become played speech, customer identity or consent. The existing transaction still requires the matching actual carrier playback receipt and a fresh caller reply. An interrupted, changed or unplayed caption cannot save a booking.
3. The conversation prompt is reduced from 11,958 to 8,679 characters. It requests short lookup acknowledgements and compact complete readbacks, including every address/postcode, date, service, window, VAT-inclusive price and payment details. The opening is shorter. Valory/v4 Turbo, GPT-4.1, Scribe, codec and normal turn/interrupt settings are retained.
4. Numeric startup timestamps identify answer callback, stream authentication, recording readiness, session setup, provider socket and first received provider audio on the next call. API diagnostics record whether the prepared URL was used, without storing a plaintext capability in metrics.

An acknowledgement before booking commit was rejected by an existing protection test: extra speech can supersede the current readback. That change was removed before deployment. Early spoken success is not used to disguise slow or unsuccessful saves.

The engineering request total is operational configuration, with a schema ceiling of 1,000. This does not authorise 1,000 calls: the actual private total remains 21, all used. Historical attempts are preserved, concurrency remains one and further calls need owner authorisation. Future approved increments do not require rebuilding source merely to change the schema ceiling.

## Verification

- Two new regressions fail against the previous gateway/runtime and pass with these changes. They cover avoiding a repeated provider HTTP request and warming caption analysis without authorising a booking.
- The backend suite passed 441 tests. Startup tests include encrypted/single-use capabilities, expired/future/mismatched URLs, double authentication, destination scoping, closed-call exclusion and preparation failure without redial.
- A real GPT-4.1 extraction with isolated Redis took 1.748 seconds initially and 0.0006 seconds from the prepared cache, with identical facts. This is a controlled component check, not a handset delay score.
- All 15 existing ElevenLabs conversation regressions passed with the shorter prompt. Two additional native checks passed for complete concise one-property and three-property landlord readbacks. These use synthetic conversations, not real phone calls or saved business actions.
- Client-reuse and compact-schema probes produced mixed latency results. They were not used to justify changing the model or the interpretation contract. The earlier smaller-model comparator failed important semantic cases, so it was not selected.

## Remaining concerns

The first identity reply in call 21 was associated with an earlier original-speech onset close to the opening boundary. The backend refused it as preceding the completed notice and the agent repeated part of the introduction. This association needs further original-audio alignment qualification; the privacy gate was not weakened to accept it. It can still add conversational delay.

Fresh handset measurement is required for the whole path and interruption behaviour. No zero-delay or human-equivalence claim is made. Carrier/network time and an authoritative save remain real costs; concise natural speech must not announce results before they exist. UK PSTN and the assessment's distinct scenario evidence remain separate qualification gates.
