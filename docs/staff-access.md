# Individual staff access

The office uses PostgreSQL identities and opaque, revocable eight-hour sessions. Passwords use salted scrypt (N=32768, r=8, p=3). Only a SHA-256 session-token digest is stored. The browser cookie is HTTPOnly, Secure, SameSite=Strict and host-only. Next forwards that person's session to the business API; the web container has no operator token or shared password.

| Username | Person | Permissions |
|---|---|---|
| mark | Mark Ellis | Administrator: office records, quality, engineering controls and team management |
| sarah | Sarah Collins | Office: customer records, follow-ups, bookings, call recordings and pause control |
| dan | Dan Hughes | Own assigned bookings only |
| priya | Priya Shah | Own assigned bookings only |
| tom | Tom Barker | Own assigned plumbing work only; existing booking policy excludes him from gas work |
| samudra | Samudra | Technical administrator, same application permissions as Mark |

The brief names five people. The sixth account above belongs to the technical owner; it does not invent an unnamed Brightwater employee. Mark's administrator role does not add him to the fixture's bookable engineers.

## Initial access

Run the additive Alembic migration before deploying the new office. Bootstrap the accounts once using a mode-0600 JSON file outside the repository and delivery ZIP. Each list item contains `username`, `name`, `role`, optional `engineer_id` and `temporary_password`. For example, run `python -m brightwater.staff_bootstrap < /private/path/accounts.json` inside the configured API environment. The command creates missing identities only and never resets an existing account. All new users must change their password before accessing business data. Keep temporary passwords private and distribute them directly to their intended users; this implementation sends no invitation emails.

At `/login`, sign in, choose a personal password of at least 14 characters, then sign in again. Changing a password revokes all existing sessions. At `/team`, administrators can reset another person's temporary password, disable or enable their account and view the latest 100 access events. Reset and disable revoke sessions immediately. Administrators cannot disable themselves; administrative changes are serialised to protect the remaining active administrator. Passwords are never displayed by the team API.

Shared `office` passwords, old signed cookies and Basic headers no longer authenticate the web app. The separate private operator token remains available for trusted operational tooling and cannot administer staff accounts. Runtime and call-scoped voice credentials retain their separate boundaries.

## Verification and limits

API integration tests cover cross-role denials, engineer filtering with mixed assignments, forced initial password changes, logout/expiry, reset/disable, salted password and token storage, generic login failures, Redis-backed throttling and broker failure. Account mutations and successful/failed sign-ins have a database audit trail. Attempts limited before password validation do not generate one audit row per rejected packet. Access-event retention/export and broader security monitoring remain deployment work.

Sign-ins are throttled by account and connection source; requests behind the same reverse proxy share a conservative source budget. Login fails closed if Redis is unavailable. Expired session rows are pruned during subsequent sign-in. Sessions expire after eight hours and are validated against account activation on every API request. In-flight requests already authorised before account disable may complete.

This is individual authentication and role enforcement. Enterprise SSO, MFA, invitation delivery, password recovery by email, authoritative staff provisioning and independent security assessment are not implemented. The fixture diary is not a production workforce directory.
