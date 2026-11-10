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
