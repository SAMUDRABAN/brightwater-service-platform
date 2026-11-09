# Assessment coverage and submission index

Reference TMG-TA-2611-01. “Implemented” does not mean handset-qualified or ready for customer production. The latest UI release does not turn earlier failed calls into passes.

| Submission item | Location | Current status |
| --- | --- | --- |
| Call flow | [Agent design](agent-design.md) | Design contract covers required outcomes, proxy, landlord and exceptions; some native branches remain unqualified |
| Instructions, opening, tool list | [Agent design](agent-design.md), `backend/src/brightwater/managed/prompt.txt`, `managed/agent.py` | Exact source and schemas supplied; private deployed resource IDs excluded |
| Campaign logic | [Agent design](agent-design.md), policy/services/worker modules | Implemented and database-tested; live UK campaign disabled |
| Questions for Mark/Sarah | [Agent design](agent-design.md) | Supplied, with reasons |
| GitHub repository and setup | Repository README | Private repository; reviewer access must be arranged by the owner |
| Six scenario recordings/transcripts with outcomes | [Evidence index](test-evidence.md), protected office call history | **Incomplete**: 20 attempts retained, not six complete distinct scenario passes |
| Sarah's morning view | `/morning` in the deployed office | Implemented: urgent-first queue, summaries/recording links, yesterday's work, campaign metrics |
| Note to Mark | [Note to Mark](note-to-mark.md) | Supplied with explicit budget assumptions and no production claim |
| Two-page handover | [Written summary](written-summary.md) | Supplied as a concise handover |

## Core requirements that remain gates

- A real outbound **UK** PSTN call and consented review number. Existing attended India calls do not meet that geographical requirement.
- Complete scenario evidence for straightforward booking, multi-property landlord, callback, do-not-call, proxy and gas smell. Backend/model tests cover these boundaries to varying degrees; they do not substitute for the six calls.
- The first-voicemail generic-message rule. Current engineering automation ends instead; a usable real office callback number and carrier qualification are needed.
- Every attempt having exactly one of the brief's 13 outcomes. Answered technical failures currently retain an unclassified result and review flag rather than falsely claiming no answer. The CRM displays “Needs review”. This taxonomy needs an agreed final treatment.
- The earlier repeated booking-confirmation and unsaved office-help findings. These remain visible and require a new attended verification.
- The optional evening-before SMS process and optional live transfer are not implemented; no SMS or transfer claim is made. A future live-diaries/notification contract must reconcile the brief's message timing.

## CRM controls checked

Follow-up resolve/reopen/assignment uses real database rows, scoped permissions, idempotency and immutable notes. It does not change call outcomes or bookings. Complaints remain assigned to Mark. Calling preferences do not clear suppression. Call exports are authenticated and neutralise spreadsheet formulas. Engineers see only their assigned diary and booking items. Unmeasured quality is explicitly labelled. Customer directory lookups are checked with more than 620 records.

All source phone numbers are fictional and blocked for dispatch. The current candidate holds 20 actual engineering attempts and two saved engineering bookings. Local browser-review fixtures are isolated from that data and labelled; they are never imported to production or used as real call evidence.
