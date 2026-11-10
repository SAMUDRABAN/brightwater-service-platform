# Automatic reminders and client-brief coverage

10 November 2026. Source release 0.4.0. These are implemented controls and engineering checks, not approval to start UK customer calls or a claim of human-equivalent conversation.

## Scheduled reminders

Celery Beat enqueues eligible work every 15 seconds through Redis. PostgreSQL retains call intent and the transactional outbox. The scheduler selects each customer once when an unresolved service/certificate falls between today and 28 days ahead, prioritising landlords and then due date. Historical overdue data does not create an endless automatic calling loop; it needs office review. Customers outside this window wait. The eight supplied fictional source numbers never become live destinations automatically.

Before both queueing and carrier admission, policy checks UK local time/DST, calling preferences, a separately registered approved destination, permanent suppression, campaign stop, unresolved calls, attempt count, spacing and used time bands. Weekdays are 10:00–19:30, Saturday 10:00–13:00, Sunday excluded. Three dispatched attempts maximum; retries require at least 24 hours, a later UK date and a different time band. A conversation stops further campaign attempts. Daily customer calling is bounded to 20 or fewer dispatches; the gateway admits one at a time and bounds customer calls to 15 minutes. The separately authorised attended-test allowance and two-hour test ceiling are unchanged.

Dispatch now uses the native ElevenLabs customer agent through an explicitly configured GB gateway, not the obsolete LiveKit campaign adapter. The GB gateway requires an approved +44 caller ID and destination, explicit campaign enablement and fresh main-server admission bound to the actual call token and destination. India remains an engineering-only route with the one privately approved recipient. Duplicate carrier requests replay a durable acknowledgement; uncertain acceptance is quarantined for review, never automatically redialled.

## Requirement matrix

| Brief requirement | Implemented behaviour | Verification / remaining limit |
|---|---|---|
| Reminder about four weeks before due | Upcoming 28-day selection, landlord priority, durable outbox and fenced Beat | Integration tests; activation remains paused |
| Calling hours and preferences | UK timezone/DST, exact published windows, restrictive customer preference | Backend policy tests |
| Three attempts and stop after conversation | Dispatched-attempt counter, 24-hour spacing, distinct time bands, stopped contact | Policy, outbox and scheduler tests |
| Caller ID | Separate real GB caller ID configuration; drama numbers blocked | Actual UK carrier/caller-ID qualification outstanding |
| Automated opening | Separate campaign opening identifies automated assistant and Brightwater in the first sentence, then recording notice | Native configuration and model checks |
| Named customer only | Existing original-speech, notice and identity gates retained; proxy cannot unlock account | Existing privacy and timing regressions |
| First voicemail only | Verified campaign voicemail claims the allowance once and returns only a short approved office callback message; no name/address/boiler | Backend tests; real approved office number still required |
| Automated menus / screening bots | No keypad navigation or bot dialogue; guarded polite end | Existing boundary regressions |
| Do not call | Durable suppression, future admission blocked, current account access stopped | Existing semantic and independent backstop tests |
| Human request | Requested callback for Sarah, office hours Mon–Fri 08:30–16:00; no invented live transfer or time guarantee | Semantic and native regressions |
| Standard prices only | £95 service / £75 CP12 / £145 combined; £60 CP12 each for three or more in one proposal; VAT included | Authoritative backend pricing tests |
| No payment collection / discounts | Engineer takes payment on the day; no replacement-work quotes or invented reductions | Agent instructions and tool contracts |
| Gas smell / CO alarm | Immediate emergency advice before tools, record and end so caller can seek help; no routine booking | Native/semantic checks; handset safety scenario still outstanding |
| Leak / no heating / no hot water | Urgent callback for Sarah with actual caller detail; blocks routine booking | Existing safety gates and new native checks |
| Complaint | Acknowledge and record for Mark; no argument or invented refund | Existing follow-up contracts |
| Other-work quote / ageing boiler | Lead for Sarah; one optional quote-interest question before the final booking readback when verified age meets configured threshold, no pressure or replacement price | Configurable 15-year assumption needs Mark's approval before customer activation |
| Arrival windows and engineer capacity | Weekday morning/afternoon, Dan/Priya gas-qualified, Tom excluded, three hours maximum per engineer/window | Database constraints, capacity races and assignment tests |
| At most two options | Tool returns no more than two sets, including requested dates/windows/engineer | Availability tests |
| Landlord multi-property / tenant contacts | One proposal for all selected properties, contacts required per property; same-day preference or agreed separate dates | Pricing/tenant and separate-day integration tests; tenant numbers never enter outbound scheduling |
| Address/window readback | Full current details plus fresh actual caller authorisation; changes/questions cannot save prematurely | Existing carrier-playback/timing and semantic checks |
| Evening-before text | Agent explains the office's text with a two-hour arrival estimate; no exact time now | Native saved-booking check; the bot does not claim it sent a text |
| Morning handover | Persistent urgent-first follow-ups, Mark complaints, summaries and protected recording links; unresolved answered conversations create one internal-review item | Backend/CRM tests; no invented callback request |
| Every attempt and outcome | Actual call rows retained; known business outcomes derive from saved events/reservations | Unknown carrier effects and answered technical failures remain explicitly flagged for review rather than falsely labelled “No answer” |
| Cost visibility | Existing quality/cost documentation and configured dispatch/duration limits | Final UK tariff, consented destination and budget qualification remain outstanding |

Gas guidance was checked against [SGN's official gas emergency advice](https://www.sgn.co.uk/smellgas): the emergency number, ventilation and avoiding flames/electrical switches are consistent with the brief. The agent gives immediate advice, without diagnosing equipment or delaying escape/help.

## Activation and validation limits

Customer calling remains off. No assessment sample number, tenant, new customer or additional owner test is dialed by this release. The successful-booking close remains short; the optional old-boiler question occurs before the final readback and fresh booking consent. The live India transport and selected Valory/model/ASR/turn settings are preserved. The separate native campaign profile has no phone number assigned automatically.

Before activation: supply and qualify the real UK carrier/caller ID, gateway and office callback; register an owned/consented UK handset; verify real customer/diary authority and the office text process; approve quote-age and spending assumptions; complete the required physical scenario artefacts and latency/voice/conversation evaluation. Configuration checks are not carrier qualification. See release-readiness.md for the broader release gates.

## Recorded engineering checks

- Full current native backend suite: **477 passed in 69.66 seconds**, including real PostgreSQL transactions, outbox/policy, UK admission, duplicate carrier requests, separate-day landlord proposals, urgent handover idempotency and the pre-readback quote offer. Ruff and version metadata passed.
- Frontend: formatting, eight tests and production build passed with the new campaign-readiness panel. GitHub PostgreSQL17/Redis and release deployment evidence is recorded separately in the package manifest.
- Actual GPT-4.1 structured checks:12 business cases passed, including natural refusal, work done elsewhere, unavailable third-party answer, quote refusal versus service refusal, urgent/no-heating/gas/CO reports, quote interest, engineer question and the non-fictional campaign notice. An initial proxy-versus-other identity-label mismatch is retained: both deny account access and the required unavailable disposition was correct.
- Actual ElevenLabs native checks:25 active cases passed for the existing phone profile and25 for the separate customer profile. Existing consent/privacy/boundary/readback cases are retained. Urgent permission-seeking and error-path closing found by earlier failed checks were corrected. The optional quote enquiry moved before the final readback; its obsolete post-save fixture is retained but retired. The phone result reuses25 valid active cases from the retained26-case invocation, whose retired fixture failed; the customer invocation ran the25 active cases. No prompt, tool or active-case input changed after the final consumed runs.
- Native tests deliberately have no real call-session credential; live webhooks therefore cannot mutate customer data. Positive tool-selection checks allow safe closing/error-handling calls while requiring the intended first write exactly once and prohibiting conflicting writes. Successful-closing behaviour uses explicit synthetic tool-result history. These checks do not establish handset voice, latency or actual carrier integration.
