# Attended call23: booking recovery

11 November 2026, version0.4.3. No new phone call was made for this repair.

## Root cause and repair

The account was a homeowner with two properties. The native model supplied tenant contacts anyway: empty phones, then national-format numbers. Tenant validation rejected preparation before creating a proposal. The generic error omitted the failed field. The agent incorrectly said Monday was unavailable, although the next diary lookup returned the same Monday offer.

The adapter now uses authoritative account.kind: homeowners prepare without tenant contacts, irrespective of unnecessary model placeholders. Landlords retain strict name and international phone validation. Both managed entry points return field paths without raw input, explicitly preserve the selected offer and distinguish input errors from capacity conflicts. Private-account, offer ownership, engineer qualification, pricing, capacity, full readback and fresh consent gates remain in force.

Identity previously always instructed the model to explain a due service even when returned obligations were empty. It now returns reminder_due and matching instructions. Additional caller-requested work remains possible; the agent must clarify the intended property/service rather than automatically choosing every property.

Callback notes previously saved only the latest assent. They now include assent, trusted recent conversation, actual arrangement status and recorded tool failures, without another model request. Phone context comes from timing-verified original caller events and completed original agent speech. Correction of an old office note is separately audited; original outcomes, recordings and failed tool events remain unchanged.

## Verification and limits

Two original homeowner regressions failed before the repair and passed afterward; the final replay covers both properties and stores no tenant contacts. Eight focused checks cover landlord validation/correction, unchanged private-account and offer gates, reminder truth, callback context/deduplication and exclusion of unverified/provider-injected history. The complete native backend suite passed486tests in77.51seconds; Ruff passes. Final PostgreSQL17/Redis CI and live checks are recorded in the release manifest.

The native phone suite passed27 of28 provider judgments. The remaining fixture omitted the original offer ID; the corrected fixture kept the same criteria and passed separately. Other cases were unchanged. The native campaign suite passed27 of28 judgments. The remaining homeowner case actually generated the required offer ID and tenants=[]. Its evaluator then labelled the honest missing-test-credential statement “I couldn’t save that booking” as a false success claim. That contradictory judgment and trace remain retained rather than reported as28 clean passes. Native tests have no phone/session credential and prove neither a real booking write nor handset quality.

Both owned agents preserve Valory, primary model, ASR and turn/interrupt configuration. Actual generated provider traces may include provider-managed fallback models; configured-primary equality is not a claim every generation used that model.

Call23 verified identity, lasted230seconds, saved a requested callback and has a protected recording. No booking was saved. No24th call is authorised. UK campaigns stay paused pending qualified routing, real office callback and recording notice. Fresh attended handset verification remains outstanding; production readiness is not claimed.


## Call24 and identity correction0.4.4

The separately authorised call24 saved one £95 boiler service, Monday16November2026 afternoon with Dan Hughes, ended after129seconds and retained its recording. The owner reported repeated name questions. The original authenticated trace shows a fresh explicit self-identification before the opening completed. The opening subsequently completed before the identity tool ran, but the tool incorrectly required disclosure to precede the volunteered name, causing a repeated opening.

The corrected rule allows a fresh, grounded self-identification to carry forward until the trusted notice completes. Account access still waits for actual disclosure completion, unchanged speaker and current original caller evidence. An early bare yes cannot answer an unheard named question; an incomplete notice or speaker change remains blocked. A completed notice is not repeated merely to obtain another name. The native prompt requires a new identity-tool check for each fresh identity reply and avoids another name request after technical authentication failure.

A second defect was isolated:0.4.3 had corrected the evaluation identity result while the trusted-phone adapter retained its own old due-service instruction. Both now use the same verified-account helper. Regressions exercise the actual trusted-phone branch with resolved/unresolved reminders as well as the volunteered-name sequence and negative cases. The two phone-reminder tests and original early-name replay failed before the correction; the final native backend suite passes491tests in77.40seconds. Final PostgreSQL17 CI and deployment verification are recorded in the manifest.

The actual semantic model interprets the original early reply as grounded self-identification. Native generated traces call confirm_identity first on the fresh name. Initial native recovery repeated the name after missing test-session credentials; explicit technical-recovery guidance corrected that generated response. A later evaluator nevertheless claimed no identity tool had been called, contradicted by the trace’s first tool. Both failed judgments remain retained, not represented as clean passes. Native fixtures have no real telephone session credential, so generated tool calls do not constitute handset verification.

No post-correction call has been placed.24of24authorised attempts are used, zero remaining. India transport, voice, primary model, ASR and interruption settings are unchanged. The original call24 booking remains saved; no additional booking was manufactured by the repair.
