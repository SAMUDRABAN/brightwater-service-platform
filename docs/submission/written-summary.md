# Technical handover summary

## Approach

I extracted the assessment into a behaviour contract before implementation: identity and privacy, scheduling, capacity, prices, follow-ups, safety and the client's morning view. The supplied eight customers and three-week diary are explicitly fictional. Implementation progressed through a transactional control plane, telephone transport, native managed conversations and the office interface. Production readiness was prioritised over the original deadline at the project owner's request; unfinished requirements are listed openly.

## Platform choice

The business API uses Python/FastAPI and PostgreSQL. Constraints, row locks and recoverable request identities protect diary capacity and booking writes. Redis, Celery and a fenced Beat scheduler support queued campaigns and reconciliation. Next.js provides the staff office with server-held sessions and role checks.

Twilio supplies the tested UK telephone route and Plivo supplies the separate domestic India route. ElevenLabs Agents supplies the deployed conversation pipeline, including the selected Valory voice, transcription, model interaction, turn-taking and native tools. Authoritative actions still run in the business API. An additional orchestration provider was not added because it would introduce another integration before the current pipeline was qualified. Direct SIP is an isolated, disabled candidate, not the selected transport. The app is hosted in London and the domestic India phone-audio gateway on a separate approved India host.

## Decisions and assumptions

Only the named customer can authorise account actions. Proxy authority is not assumed. A changed or interrupted readback cannot reuse an earlier yes. Natural agreement is interpreted in context rather than matched against a few phrases, with independent binding to the current caller, proposal and completed speech. Gas work excludes Tom. Prices are integer pence, arrival windows are not exact times, and current availability is checked again transactionally.

The assessment numbers are never dialled. Attended calls use separately approved destinations and fictional customer records. Customer calling is paused. Misuse and automation safeguards protect genuine requests and preserve saved bookings. The first voicemail message is implemented and still needs a handset playback check.

## Testing and findings

Checks include real PostgreSQL/Redis integration, capacity races, idempotency, stale/interrupted speech, natural consent/cancellation, denial of other-account actions, personal logins and engineer data isolation. The office redesign adds audited follow-up actions, customer preferences, searchable call history, safe CSV output and engineer-scoped booking details. Browser checks use an isolated review database; illustrative screen records are not claimed as phone evidence.

Early India tests exposed carrier packet, buffering, recording and playback-receipt defects. Those failures remain in the audit record. The 11 November UK call saved the £95 boiler service with Priya Shah and delivered the spoken confirmation. The [evidence index](test-evidence.md) pairs six scenario records with outcomes and identifies the spoken opt-out gap. The UK transcript also repeats a diary acknowledgement. Voice quality and latency have yet to be measured independently.

## Risks and remaining work

The assessment review still needs its live call to the agreed recipient. Verify first-voicemail playback and the spoken opt-out acknowledgement, and agree how to classify answered technical failures. Measure end-to-end latency and interruptions on the real carrier before customer activation. Before customer production, establish the live diary, actual callback arrangements, privacy/retention approval, operational monitoring, recovery drills and independent security/accessibility checks. Individual roles are implemented; enterprise SSO/MFA and high availability are not claimed.

## Tools and learning

I used Codex for research, implementation and test orchestration; gstack for browser review; Python/Node tooling for extraction, validation and builds; and the real provider APIs for bounded engineering checks. I reviewed generated changes and retained contradictory/failed evidence. The most useful lesson was that a model's correct intent or a local test does not prove carrier playback, audible quality or a successfully saved customer action. Those require separate evidence.
