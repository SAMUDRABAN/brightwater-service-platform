# Changelog

## [0.4.3] - 2026-11-11

- Prepare homeowner visits without unnecessary tenant data; retain strict landlord contact validation. Return specific field errors without raw input or unsupported availability changes.
- Derive reminder language from unresolved obligations and save callback assent with trusted recent conversation, actual booking status and tool failures.
- Add attended-call regressions and native recovery cases. Preserve voice, primary model, ASR and interruption settings. No additional phone call is authorised or placed by the repair.

## [0.4.2] - 2026-11-10

- Return before customer scans when the daily call budget is exhausted, and bulk-read campaign contact state. A620-customer integration check ensures the scheduler takes no booking advisory locks in the exhausted case, protecting live booking latency.

## [0.4.1] - 2026-11-10

- Restore all third-party dependency pins after the release version update accidentally changed an unrelated 0.3.1 dependency to a non-existent 0.4.0. Only the Brightwater package version changes. CI and image build rejected 0.4.0 before activation; the live deployment was unaffected.

## [0.4.0] - 2026-11-10

- Route automatic 28-day reminders to a separately gated native ElevenLabs UK campaign, removing the legacy LiveKit dispatch path. Keep India attended tests isolated.
- Add approved-destination admission, landlord priority, bounded queue lookahead, daily call cap, exact UK calling hours and campaign readiness shown in the CRM.
- Complete brief behaviours: semantic refusal/serviced-elsewhere/unavailable outcomes, one approved campaign voicemail, urgent-first unresolved handover, evening-before text notice and one optional ageing-boiler quote enquiry.
- Allow agreed separate-day landlord visits in one correctly priced proposal. Retain diary capacity, qualification and original-speech consent guards.
- Preserve Valory, model, ASR and turn/interrupt settings. Customer campaigns remain paused pending real UK carrier/caller-ID/callback qualification; no new physical calls are made by this release.

## [0.3.1] - 2026-11-10

- Derive the automatic call-end summary from the actual saved booking, preventing a contradictory “no arrangement” summary beside a confirmed reservation. Preserve specific staff/provider summaries.
- Reconcile the legacy automatic summary only where an actual confirmed booking exists, retaining its prior text in an audit event. No booking, transcript or outcome is changed.

## [0.3.0] - 2026-11-10

- Keep the selected proposal through questions and expose authoritative arrangement status to voice and CRM.
- Honour optional calendar date, arrival-window and named engineer preferences using real diary capacity and qualifications; never silently substitute a requested engineer.
- Return actual assigned engineers after saving; link call records directly to bookings and show proposed versus confirmed visits.
- Reuse unchanged offers/proposals, reject assignment changes before saving, and prevent another confirmed proposal in the same call.
- Answer information questions before treating assent as booking consent; brief questions and duplicate tool retries do not exhaust the full-readback recovery budget.
- Disable preparation acknowledgements that could imply premature success. Retain Valory and existing interruption settings.
- Accept the provider's current signed connection URL format for encrypted, single-use prewarming; retain fallback and admission checks.
- Preserve native test tool IDs across provider reprovisioning. Add engineer-question and selected-date native regressions.

Owner call22 saved the combined £145 visit with Priya Shah. These changes have not yet had a further handset comparison; UK customer calling remains disabled.

## 0.2.2 — 10 November 2026

- Prepare an encrypted, single-use provider connection URL while an authorised phone rings, with the existing authenticated active-call gate and normal fallback.
- Prefetch readback language analysis from captions during speech; saved actions still require actual completed carrier playback and a subsequent caller reply.
- Shorten the conversation prompt and opening; retain concise complete one-property and landlord readback regression cases.
- Capture numeric startup stages for the next attended comparison. Voice, model, audio codec and turn/interrupt settings remain unchanged.
- Allow operational test totals to be configured without a code release; the actual private allowance remains 21 with 21 used and no additional phone call authorised.

## 0.2.1 — 10 November 2026

- Permit a configured twenty-first attended engineering attempt after explicit owner authorisation. The deployed private allowance determines actual admission; historical attempts are preserved.
- The owner initiates the additional test through the CRM. UK campaign controls and approved-recipient restrictions remain unchanged.

## 0.2.0 — 10 November 2026

### Added

- Brightwater-branded office redesign with a restrained application frame, supplied SVG assets and locally hosted brand fonts.
- Audited, idempotent follow-up completion, reopening and assignment; complaints remain assigned to Mark.
- Customer property/reminder views, saved UK-local calling preferences and protected consented-number registration.
- Searchable, paginated call history with recording/transcript access and CSV export with formula neutralisation.
- Engineer-scoped weekly diary and booking detail views.
- Updated voice-quality presentation, personal access pages and release/submission documentation.
- CRM permission, idempotency, scalability, British formatting and CSV safety checks.

### Preserved

- Existing call, booking, suppression and recording records; authoritative booking and gas-engineer constraints.
- Selected Valory/ElevenLabs voice settings, interruption behaviour and the separate India engineering route.
- Paused customer calling, the twenty-attempt budget and the requirement for fresh attended-call authorisation.

### Qualification still required

UK PSTN qualification, six scenario-specific attended call artefacts, independent voice/latency ratings, the prior confirmation-loop/office-help findings, direct SIP qualification and broader production operations. See the assessment coverage and release-readiness documents. This release is not a declaration that every assessment or production gate is complete.
