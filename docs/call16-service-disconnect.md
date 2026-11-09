# Sixteenth attended call: service disconnect investigation

9 November 2026. Status: investigation incomplete; calling paused.

The owner authorised one attended test, capped at three minutes. It exercised a separate explicitly fictional CP12 obligation priced at £75 including VAT. The previously saved boiler booking was preserved; no booking or cancellation occurred on call 16.

The owner confirmed the service disconnected. The gateway recorded `AudioTransportError` / `playback_checkpoint_timeout`, ElevenLabs reported client disconnect 1011, and the authenticated carrier CDR reports API Request / Normal Hangup after 40 seconds. This is a transport failure, not a customer hang-up or business refusal. The protected recording is stereo, 39.3665 seconds, 670632 bytes; anonymous access returns 401 and operator access 200.

The agent repeated its opening identity question. The provider preserved “Yes, you are” and later “Yes, I am Samudra Banerjee.” Identity did not verify before the disconnect. The earlier original-onset versus transcript alignment discrepancy remains under investigation; these observations do not establish that the caller answered too early.

## Confirmed diagnostic defect and limited change

Transport failure cleared the pending-checkpoint map before the managed diagnostic captured it. The retained call 16 data therefore cannot establish whether the missing acknowledgement was a final checkpoint, stalled playback or another ordering problem. Both responses had complete provider text/alignment and captured PCM; that does not prove completed carrier playback.

The new diagnostic takes a bounded numeric snapshot before cleanup: pending/sent/final checkpoint counts, oldest age, outstanding samples, acknowledged-count/age, queue counts and generation. No audio, checkpoint identifiers, credentials or phone numbers enter this snapshot. It is attached to the existing encrypted 24-hour private diagnostic. Logging remains optional and cannot suppress the primary error. Timeout thresholds, consent proofs, checkpoint semantics and business actions are unchanged.

The regression fails against the preceding transport because the snapshot does not exist, then passes with the change. The managed diagnostic test verifies encryption, 24-hour retention, numeric snapshot preservation and propagation of the primary failure when the store is unavailable. This repairs missing diagnostic evidence; it is not a verified repair for the carrier timeout.

## Next qualification

Reproduce the pending-ACK ordering offline before changing transport semantics. Correlate native transcript timing with original caller speech spans before changing identity onset association. Resume the six-stage latency and direct-SIP qualification plan after resolving these failures. Native SIP remains disabled and unassigned; no business guard may be removed to enable it. No seventeenth call is authorised, and no automatic redial is scheduled. All 16 attempts are used. UK campaign controls remain off.

Offline replay of both saved stereo channels found a brief caller-channel speech span around 2.8–3.36 seconds and the next around 15.6–16.64 seconds; the agent-channel opening spans approximately 4.5–14.7 seconds. This supports investigating a stale pre-opening onset being assigned to the later reply. VAD identifies speech spans, not words; it does not alone prove transcript association. No onset association policy has been changed. The replay used the existing recording and local model, with no phone or paid transcription call.

Native backend: 355 tests passed in 110.30 seconds. All 21 transport tests passed, including the new pre-cleanup snapshot regression. Ruff and whitespace checks passed. The initial encrypted-store fixture lacked the newly required snapshot field; that test fixture was corrected and the full native suite rerun. Linux validation and deployment are recorded below when completed.

Exact committed runtime `5bb22ce78d7357b983b36156e6e8f77bd051bcaa` passed 355 Linux/PostgreSQL17 tests in 150.93 seconds. The earlier intermediate Linux run failed because its diagnostic test double lacked the snapshot property; its failure is retained, and the corrected exact-source suite passed. The diagnostic release is deployed with admission disabled; this does not qualify a repaired handset conversation.
