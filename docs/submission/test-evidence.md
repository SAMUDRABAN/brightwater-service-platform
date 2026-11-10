# Test evidence and its limits

Actual owner-attended attempts and recordings are retained in the protected office call history, under “Engineering tests”. The source repository does not contain private caller audio, credentials or the original assessment PDF. Review access and any release of redacted recordings need to be arranged separately; no assessor was emailed or invited by this release.

| Evidence | Meaning |
| --- | --- |
| 21 retained attended attempts | Actual carrier activity, including failures; not 21 successful scenarios |
| Attempts15 and18 | Two saved fictional bookings, with protected recordings. Attempt18 saved the £75 CP12 visit and closed normally |
| Attempt19 | Owner preferred Valory/interruption handling; office-help request was not saved |
| Attempt20 | Identity and proposals occurred, no new booking; repeated confirmation and the old duration cutoff were findings |
| Backend/PostgreSQL/Redis checks | Authority, transactions, capacity, idempotency, consent, permissions, queue and CRM behaviour; no new physical calls |
| Native ElevenLabs/model simulations | Tool/intent/prompt checks, including retained errors and harness corrections; not handset or real business-write proof |
| Generated auditions and operational farewell check | Actual provider audio generation; not independent voice quality or carrier playback evidence |
| Isolated browser-review dataset | UI interactions, filters, forms and responsive layouts only; explicitly not PSTN evidence |

Attempt 21 saved a third fictional booking and ended normally; the owner reported slow opening/replies. The latency candidate is described in [call21-latency.md](../call21-latency.md), with no new handset-speed claim.

Detailed historical reports remain in `docs/`, including the call15–20 and contextual-boundary reports. They record defects and corrections rather than replacing failed evidence with polished summaries.

The six required scenario-specific telephone artefacts remain a submission gate. No extra call is authorised by publishing code. All 21 authorised attempts have been used; no further telephone call is authorised.
