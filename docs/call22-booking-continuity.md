# Call 22: booking continuity, engineer assignment and CRM checks

10 November 2026. Engineering release 0.3.0, following owner feedback on call 22. No further handset call was placed by this release work.

## What actually happened

The attended call saved a combined service and CP12 visit on Monday 16 November 2026, afternoon, with Priya Shah, total £145 including VAT. The call ended normally after approximately 305 seconds. All 22 attempts and four saved fictional bookings remain retained. The owner reported somewhat better response timing, but repeated dates and difficulty completing some booking exchanges.

The database had saved the final booking correctly. Earlier in the same call, an engineer question interrupted preparation, the agent lacked the actual engineer information, and short follow-up questions were incorrectly consuming the readback-recovery budget. The agent restarted availability rather than keeping the selected proposal. Offers legitimately remain available until a reservation is saved; presenting them again without explaining the pending state caused confusion.

## Changes

- Verified accounts return actual active engineers, eligibility and the current UK calendar date. Availability supports optional date, arrival-window, named engineer and later-date preferences. Requested engineers are never silently substituted; Tom remains excluded from gas work.
- Availability reads reuse unchanged unexpired offers; preparation reuses the same unchanged unexpired proposal. Neither holds diary space. Same-day landlord visits may span morning and afternoon where capacity requires it.
- Preparation and atomic saving recheck the actual window date, period, assigned engineer and qualifications. Capacity locks and scope/consent checks remain. A second confirmed proposal in one call is rejected rather than creating a duplicate.
- A read-only `review_arrangement` tool returns the selected proposal or saved arrangement, including real engineer names and explicit saved/reserved status. Confirmation returns the same database read model used by the CRM call detail.
- Whole-reply semantic instructions explicitly treat an unresolved information question as a question despite affirmative wording. The agent answers it before the full current readback. Brief questions, interruptions and duplicate retries do not consume the two-substantial-readback recovery budget. Full actual playback and fresh original caller evidence are still required to save; no booking guard was relaxed.
- Preparation pre-tool speech is off to prevent premature “saving” claims. Availability acknowledgements remain. Valory, GPT-4.1, ASR, turn-taking, interruption and privacy settings are retained.
- CRM call details distinguish selected/awaiting confirmation, expired/not booked and confirmed arrangements, show actual proposed/assigned engineers and link directly to the saved booking.
- Provider reprovisioning preserves standalone business tool IDs used by native regressions.

## Startup finding

Call22 used the fallback connection URL request: the provider now returns `conversation_signature`, while the warm-up parser required the older `token` query. The parser now accepts exactly one credential form, with host/path/agent binding unchanged. An actual provider URL and encrypted single-use Redis consumption passed without dialing. This establishes compatibility, not a measured handset latency improvement.

## Verification

- Native PostgreSQL integration suite:460 passed in 67.62 seconds; Ruff and version consistency passed.
- Actual GPT-4.1 whole-reply checks:7/7 passed, including the owner's engineer-choice question, unconditional/frustrated agreement, a conditional change, withdrawal and cancellation. Synthetic text only; no business writes.
- Actual ElevenLabs native phone regressions:19/19 passed, including retained consent/privacy/boundary/closing/readback cases and new engineer-question/selection-continuity cases. Attached to the owned agent. These test generated behaviour, not handset audio or real tool execution.
- Office formatting, 8 tests and production TypeScript/Next build passed. Further deployment/CI/live verification is recorded in validation.md when complete.

## Limits

No claim of instantaneous replies, human equivalence or full production qualification. The real phone integration still includes hosted language/tool round trips and India–London network travel. The latest fixes require a separately authorised attended handset comparison. UK route/recipient, complete assessment-specific call artefacts, independent voice/conversation ratings and remaining operational release gates are still outstanding. Ordinary UK campaign dialing remains off;22/22 authorised engineering attempts are used.

## Visual check correction (0.3.1)

The authenticated server-render inspection found a legacy automatic summary saying no arrangement was completed despite the saved booking. Call finalisation now derives that fallback from actual booking facts. The existing recorded fallback is reconciled only for calls with a confirmed booking, with an audit event retaining the previous text; specific staff summaries, transcripts, outcomes and reservations are preserved. This repair changes no provider prompt or audio settings.
