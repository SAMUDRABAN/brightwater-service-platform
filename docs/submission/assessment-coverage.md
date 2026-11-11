# Assessment coverage and submission index

Reference TMG-TA-2611-01. “Implemented” does not mean handset-qualified or ready for customer production. The latest UI release does not turn earlier failed calls into passes.

| Submission item | Location | Current status |
| --- | --- | --- |
| Call flow | [Agent design](agent-design.md) | Design contract covers required outcomes, proxy, landlord and exceptions; some native branches remain unqualified |
| Instructions, opening, tool list | [Agent design](agent-design.md), `backend/src/brightwater/managed/prompt.txt`, `managed/agent.py` | Exact source and schemas supplied; private deployed resource IDs excluded |
| Campaign logic | [Agent design](agent-design.md), policy/services/worker modules | Implemented and database-tested; live UK campaign disabled |
| Questions for Mark/Sarah | [Agent design](agent-design.md) | Supplied, with reasons |
| GitHub repository and setup | Repository README | Public source repository; staff access and private recordings remain protected |
| Six scenario recordings/transcripts with outcomes | [Evidence index](test-evidence.md), protected office call history | Six real scenario records located with saved outcomes, transcripts and recordings. Spoken opt-out playback remains open. |
| Sarah's morning view | [Sarah’s morning view](https://office.46.101.11.137.sslip.io/morning), staff login required | Implemented: urgent-first queue, summaries/recording links, yesterday's work, campaign metrics |
| Note to Mark | [Note to Mark](note-to-mark.md) | Supplied with explicit budget assumptions and no production claim |
| Two-page handover | [Written summary](written-summary.md) | Supplied as a concise handover |

## Verified UK test

The 11 November 2026 20:19 UK call completed via Twilio and ElevenLabs. It verified identity, saved a £95 boiler service with Priya Shah in the diary and delivered the booking confirmation. The protected recording and transcript are indexed with the five other scenario records. [Attended call evidence](test-evidence.md)

## Remaining review and customer launch checks

- **Live review.** Trigger a call to the assessor's agreed number during the review and open the resulting CRM record. The successful UK rehearsal closes the UK route and straightforward booking evidence gap.
- **Voicemail and opt-out.** Verify complete first-voicemail playback with an approved office callback number, and verify the full spoken opt-out acknowledgement on a fresh consented test. Permanent suppression was saved in the existing test.
- **Outcome taxonomy.** Agree how to map answered technical failures to the brief's 13 outcomes. The CRM retains unresolved attempts as **Needs review**, with an evidence-based staff review action.
- **Conversation and quality.** Check the diary acknowledgement duplication in the transcript against handset audio, and verify the refusal goodbye. The callback record covers booking recovery. Broader interruption and latency checks remain part of customer launch qualification.
- **Customer launch.** Automatic calling stays paused. Verify the real office callback route and production campaign permissions, authoritative diary and notification arrangements, including delivery of the evening-before text. Live transfer is optional.

## CRM controls checked

Follow-up resolve/reopen/assignment uses real database rows, scoped permissions, idempotency and immutable notes. It does not change call outcomes or bookings. Complaints remain assigned to Mark. Calling preferences do not clear suppression. Call exports are authenticated and neutralise spreadsheet formulas. Engineers see only their assigned diary and booking items. Unmeasured quality is explicitly labelled. Customer directory lookups are checked with more than 620 records.

All assessment sample numbers are fictional and blocked for dispatch. Browser-review fixtures are labelled and excluded from the telephone evidence.
