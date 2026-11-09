# Technical handover summary

## Approach

I extracted the assessment into a behaviour contract before implementation: identity and privacy, scheduling, capacity, prices, follow-ups, safety and the client's morning view. The supplied eight customers and three-week diary are explicitly fictional. Implementation progressed through a transactional control plane, telephone transport, native managed conversations and the office interface. Production readiness was prioritised over the original deadline at the project owner's request; unfinished requirements are listed openly.

## Platform choice

The business API uses Python/FastAPI and PostgreSQL. Constraints, row locks and recoverable request identities protect diary capacity and booking writes. Redis, Celery and a fenced Beat scheduler support queued campaigns and reconciliation. Next.js provides the staff office with server-held sessions and role checks.

Plivo supplies the existing owned number and telephone route. ElevenLabs Agents supplies the deployed conversation pipeline, including the selected Valory voice, transcription, model interaction, turn-taking and native tools. Authoritative actions still run in the business API. An additional orchestration provider was not added because it would introduce another integration before the current pipeline was qualified. Direct SIP is an isolated, disabled candidate, not the selected transport. The app is hosted in London and the domestic India phone-audio gateway on a separate approved India host.

## Decisions and assumptions

Only the named customer can authorise account actions. Proxy authority is not assumed. A changed or interrupted readback cannot reuse an earlier yes. Natural agreement is interpreted in context rather than matched against a few phrases, with independent binding to the current caller, proposal and completed speech. Gas work excludes Tom. Prices are integer pence, arrival windows are not exact times, and current availability is checked again transactionally.

The assessment numbers are never dialled. The owner consented to an India-only attended test destination; this does not satisfy the UK PSTN requirement. Customer calling is paused. The newer misuse/automation safeguards protect genuine requests and preserve saved bookings. Their no-message voicemail behaviour differs from the brief and remains a documented gap.

## Testing and findings

Checks include real PostgreSQL/Redis integration, capacity races, idempotency, stale/interrupted speech, natural consent/cancellation, denial of other-account actions, personal logins and engineer data isolation. The office redesign adds audited follow-up actions, customer preferences, searchable call history, safe CSV output and engineer-scoped booking details. Browser checks use an isolated review database; illustrative screen records are not claimed as phone evidence.

Twenty attended engineering attempts are retained. Early failures exposed real carrier packet, buffering, asynchronous recording and playback-receipt defects. Those were corrected without discarding failures or weakening consent. Two calls saved fictional bookings. Owner feedback preferred Valory and improved interruptions; pauses, a later confirmation loop and an unsaved office-help request remain concerns. Generated auditions, model simulations and native provider tests are not a listening study or evidence that every scenario passed.

## Risks and remaining work

Before submission qualification, complete a supported UK test route, six distinct attended scenarios, a reviewer-triggered call with recorded consent and the brief's voicemail handling. Resolve the conversation findings, then measure end-to-end latency and interruptions on the real carrier. Before customer production, establish the live diary, actual callback arrangements, privacy/retention approval, operational monitoring, recovery drills and independent security/accessibility checks. Individual roles are implemented; enterprise SSO/MFA and high availability are not claimed.

## Tools and learning

I used Codex for research, implementation and test orchestration; gstack for browser review; Python/Node tooling for extraction, validation and builds; and the real provider APIs for bounded engineering checks. I reviewed generated changes and retained contradictory/failed evidence. The most useful lesson was that a model's correct intent or a local test does not prove carrier playback, audible quality or a successfully saved customer action. Those require separate evidence.
