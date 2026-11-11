# Brightwater Service Platform

A branded office CRM and outbound service-reminder candidate for **Brightwater Plumbing & Heating Ltd**, built for The Meraki Group assessment `TMG-TA-2611-01`.

**Version 0.4.4 · engineering candidate.** Customer calling is paused. An attended UK call through Twilio and ElevenLabs saved a fictional £95 boiler service in the diary on 11 November 2026. The CRM holds six scenario records with transcripts, recordings and saved outcomes. See the [evidence index](docs/submission/test-evidence.md) and [remaining checks](docs/submission/assessment-coverage.md#remaining-review-and-customer-launch-checks).

[Office login](https://office.46.101.11.137.sslip.io/login) · [Assessment coverage](docs/submission/assessment-coverage.md) · [Note to Mark](docs/submission/note-to-mark.md) · [Technical handover](docs/submission/written-summary.md)

## Booking recovery

An earlier attended test exposed unnecessary homeowner tenant validation. The adapter now omits homeowner tenant fields, returns specific validation recovery and distinguishes input failures from diary capacity. Reminder wording follows actual unresolved obligations; callback notes retain assent and business context. India attended attempt 23 saved an office callback after booking recovery. [Repair evidence](docs/booking-recovery.md).

## Automatic reminders

The server-side campaign now selects upcoming 28-day reminders, prioritises landlords and dispatches through a separately gated native ElevenLabs UK route. Redis/Celery/Beat handle durable scheduling and retries; the active conversation keeps its direct tool/database path. The CRM Call controls page shows due counts and activation blockers. The UK attended route has saved a booking. Automatic customer calling stays paused pending campaign and office callback sign-off. The India route is for attended tests. [Brief coverage and checks](docs/campaign-and-brief-coverage.md) · [UK route qualification checklist](docs/uk-route-qualification.md).

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
                         Twilio UK gateway / Plivo India gateway
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

- Use a separately consented recipient for each attended test. Assessment sample numbers remain blocked. UK campaign and attended-call admission are separate.
- The reviewer live call is a separate assessment step. First-voicemail playback, the spoken opt-out acknowledgement and treatment of unclassified answered failures still need verification or agreement.
- The UK booking call completed identity and confirmation without a retry. Its transcript repeats the diary acknowledgement. The saved callback evidence is from booking recovery.
- Independent voice/conversation ratings, complete end-to-end latency measurements, enterprise SSO/MFA, live-diary integration, monitoring and recovery/high-availability qualification remain work.

See [release readiness](docs/release-readiness.md), [call-purpose safeguards](docs/call-purpose-boundaries.md), [changelog](CHANGELOG.md), [engineering conventions](docs/engineering-conventions.md) and [ownership notices](NOTICE.md). Historical implementation notes are retained under `docs/`; current status above and in the assessment coverage takes precedence over earlier checkpoints.

## Interface preview

See the [desktop and mobile interface review](docs/screenshots/README.md). The screenshots contain isolated review fixtures, not production call evidence.
