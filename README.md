# Brightwater Service Platform

A branded office CRM and outbound service-reminder candidate for **Brightwater Plumbing & Heating Ltd**, built for The Meraki Group assessment `TMG-TA-2611-01`.

**Version 0.4.1 · engineering candidate.** Customer calling is paused. The office is deployed, 22 owner-attended engineering attempts are retained and four fictional bookings were saved. The physical tests used India; a UK route and six complete scenario-specific telephone artefacts remain qualification gates. This is not a claim of production readiness or full assessment completion.

[Office login](https://office.46.101.11.137.sslip.io/login) · [Assessment coverage](docs/submission/assessment-coverage.md) · [Note to Mark](docs/submission/note-to-mark.md) · [Technical handover](docs/submission/written-summary.md)

## Automatic reminders

The server-side campaign now selects upcoming 28-day reminders, prioritises landlords and dispatches through a separately gated native ElevenLabs UK route. Redis/Celery/Beat handle durable scheduling and retries; the active conversation keeps its direct tool/database path. The CRM Call controls page shows due counts and activation blockers. Customer calling is still paused until a real UK route/caller ID and office callback are qualified. The India route remains attended-test only; no new calls are authorised by this release. [Brief coverage and checks](docs/campaign-and-brief-coverage.md).

## What the office does

- **Morning overview:** urgent-first follow-ups with summaries and recording links, bookings made yesterday and customer-campaign progress.
- **Follow-ups:** complete, reopen and assign work with persistent state, request idempotency and an immutable note trail. Complaints stay with Mark.
- **Customers:** find records, inspect properties/reminders, save UK-local calling preferences and register a separately consented calling destination. Preferences never override suppression.
- **Diary and bookings:** inspect real capacity, arrival windows and saved visits. Dan/Priya carry out gas work; Tom is excluded. Engineers see only their own work and booking details.
- **Call history:** search/filter/paginate attempts, inspect original outcomes and transcripts, play protected recordings and export CSV. Unclassified technical failures are shown honestly as needing review.
- **Access and controls:** personal logins, mandatory initial password changes, revocable sessions, server-side role restrictions, pause control and a separate bounded attended-test route.

The interface follows the supplied Brightwater logo, navy/orange palette and Manrope/Inter typography. Fonts are served locally. It takes layout/hierarchy inspiration from ElevenLabs without copying its brand or proprietary assets. [Design decisions](DESIGN.md).

## Architecture

```text
Next.js office ── individual staff session ── FastAPI business API
                                               │
                               PostgreSQL transactions / audit
                                               │
                         Redis ── Celery workers / fenced Beat
                                               │
                            approved call intent / admission
                                               │
                      Plivo phone network ↔ India media gateway
                                               │
                                ElevenLabs native conversation
                                               │
                         scoped tools → authoritative business API
```

PostgreSQL controls identity-scoped actions, prices, capacity and idempotency. ElevenLabs supplies the selected Valory/v4 Turbo conversation pipeline; business results are never fabricated in the prompt. Carrier recording and playback receipts remain separate evidence. The London office and India domestic engineering route are distinct. Direct SIP is disabled/unassigned pending qualification.

## Run locally

Prerequisites: Docker Engine with Compose v2; Python 3.12+. For native development also use Node.js 24, pnpm 10.22.0 and uv 0.11.19.

```sh
python3.12 scripts/configure_local.py --output .env
docker compose --env-file .env up --build -d
docker compose --env-file .env run --rm api brightwater seed
```

Configuration is generated privately with unique credentials. `.env.example` documents the variables with provider secrets blank. The eight customers and pre-existing diary blocks are labelled assessment fixtures. No customer number is enabled for dispatch.

Create private staff bootstrap credentials **outside** the repository, then load them once:

```sh
python3.12 scripts/create-staff-bootstrap.py \
  --output "$HOME/.config/brightwater/local-staff.json"
docker compose --env-file .env exec -T api \
  python -m brightwater.staff_bootstrap \
  < "$HOME/.config/brightwater/local-staff.json"
```

Open <http://localhost:3000/login>. Read the private file locally for the unique temporary passwords. Each person must choose a personal password on first sign-in. Bootstrap only creates missing accounts; it does not reset existing ones. No password, shared fallback or operator token is shipped to the browser. See [staff access](docs/staff-access.md) for role details and deployment limitations.

## Verify

```sh
python3.12 scripts/check-version.py
cd backend
uv sync --frozen --extra dev --extra voice
uv run ruff check src tests
uv run alembic upgrade head
uv run alembic check
uv run pytest -q
cd ../web
pnpm install --frozen-lockfile
pnpm format:check
pnpm test
pnpm build
```

**Tests reset their database.** Supply a private `BW_TEST_ENV_FILE` with `BW_ENVIRONMENT=test`, an isolated database URL containing `/brightwater_test`, Redis and distinct credentials. Do not use a deployed database. The test guard refuses other environments. Provider/phone evaluations are separate, explicitly invoked checks; normal CI must not dial or require production provider keys.

[CI](.github/workflows/checks.yaml) runs isolated PostgreSQL 17/Redis 7.4 backend checks and the office production build. Native tests cover calling policy, capacity races, identity/consent, idempotency, staff isolation and CRM actions. Generated/model tests are not handset-quality ratings. See [validation](docs/validation.md) for exact recorded results, including failed evidence and its limits.

## Assessment handover

| Item | Read here |
| --- | --- |
| Flow, prompt, tools and campaign design | [Agent design](docs/submission/agent-design.md) |
| Questions before customer use | [Agent design: questions](docs/submission/agent-design.md#questions-before-real-customers) |
| Setup and source | This README and [contribution guide](CONTRIBUTING.md) |
| Actual call evidence / missing scenarios | [Evidence index](docs/submission/test-evidence.md) |
| Sarah's morning view | Deployed `/morning`, protected by personal login |
| One-page client note | [Note to Mark](docs/submission/note-to-mark.md) |
| Short colleague handover | [Written summary](docs/submission/written-summary.md) |
| Outstanding criteria | [Assessment coverage](docs/submission/assessment-coverage.md) |

Private caller recordings, credentials, database dumps and the original assessment PDF are intentionally outside the repository. The repository is public; the owner must arrange protected office access and share any approved call artefacts separately. Publishing source does not email or submit the assessment.

## Current boundaries

- Never dial assessment drama numbers or an unconsented destination. UK campaign calling and the separate attended route have independent admission gates. The twenty-attempt allowance is exhausted; another physical attempt requires fresh authority.
- The brief's first-voicemail message, strict outcome taxonomy for answered technical failures, six distinct scenario recordings and UK recipient requirement remain explicit gates.
- Call 20's repeated-confirmation and call 19's unsaved office-help findings remain open. A CRM redesign does not resolve them.
- Independent voice/conversation ratings, complete end-to-end latency measurements, enterprise SSO/MFA, live-diary integration, monitoring and recovery/high-availability qualification remain work.

See [release readiness](docs/release-readiness.md), [call-purpose safeguards](docs/call-purpose-boundaries.md), [changelog](CHANGELOG.md), [engineering conventions](docs/engineering-conventions.md) and [ownership notices](NOTICE.md). Historical implementation notes are retained under `docs/`; current status above and in the assessment coverage takes precedence over earlier checkpoints.

## Interface preview

See the [desktop and mobile interface review](docs/screenshots/README.md). The screenshots contain isolated review fixtures, not production call evidence.
