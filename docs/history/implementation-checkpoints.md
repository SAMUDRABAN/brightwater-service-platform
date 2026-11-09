# Historical implementation README

Archived text only. The current repository README and assessment coverage take precedence. These checkpoints are not new qualification claims.

````markdown
# Brightwater office and voice agent

An implemented calling-policy and booking control plane, branded office UI and direct Plivo/LiveKit voice adapter. **This is an engineering candidate, not a production-qualified release.** UK customer calling is disabled. The London office and dedicated India voice host are deployed with HTTPS. Twenty attended engineering calls have been attempted. Call15 saved one fictional engineering booking; calls16 and17 failed with playback-checkpoint timeouts and no new booking. Call18 saved a fictional £75 CP12 booking and closed normally after the playback receipt repair. Calling is paused. Measured conversation/latency and UK production qualification remain incomplete. See the current deployment and voice reports.

Current native caller: **Valory B / ElevenLabs v4 Turbo**. [Contextual call-purpose controls](docs/call-purpose-boundaries.md) protect legitimate enquiries while ending persistent misuse and clear automated answerers. Calling remains paused; no handset qualification is inferred from automated checks.

The assessment business, eight customers, telephone numbers and diary are fictional. The API uses PostgreSQL transactions and live queries; it does not return canned booking successes. The diary's pre-existing occupancy is explicitly labelled assessment fixture data. Never dial the sample numbers. Only separately registered destinations with recorded agreement are eligible.

## What exists

- FastAPI business API; distinct operator, runtime and short-lived call credentials; suppression and calling policy enforced outside the model.
- PostgreSQL schema and Alembic migration; durable call intents/outbox; Redis/Celery dispatch, maintenance and reconciliation queues; Beat with a database leadership lock checked before scheduling.
- Versioned booking proposals, completed read-back/affirmative requirements, concurrent capacity locking and idempotent booking recovery handles. Gas work excludes Tom.
- LiveKit outbound SIP adapter for a configured Plivo Zentrunk; the voice worker must report readiness before a SIP request. Unknown initiation results are quarantined for review rather than redialled.
- Voice tools for verified account access, diary checks, landlord contacts, booking, opt-out, escalation and emergency handling. The runtime explicitly configures semantic turn detection, Silero VAD and adaptive interruptions, and captures caller/assistant transcript and server-side turn events. These are unqualified settings, not handset timing measurements. An authenticated upload stores session Ogg recordings encrypted at rest, and the office has protected call-detail playback. Actual call recording capture and disaster recovery still require end-to-end qualification.
- Next.js office views for morning work, follow-ups, bookings, customers, call controls and quality status. API credentials stay on the server. Empty views and unmeasured quality remain explicit.
- Linux containers deployed and tested on the London host; isolated test databases/networks; shadow configuration and remote CI definitions. Remote CI and independent shadow infrastructure remain unverified.

## Run locally with Docker

Prerequisites: Docker Engine/Desktop with Compose v2 and Python 3.12+. From this directory:

```sh
python3 scripts/configure_local.py --output .env
docker compose --env-file .env up --build -d
docker compose --env-file .env run --rm api brightwater seed
```

Open <http://127.0.0.1:3000/morning>. API liveness/readiness: <http://127.0.0.1:8787/health/ready>. The generated private file has unique credentials and mode 0600, and is excluded from version control. Do not copy local credentials into another environment. The generator refuses to overwrite existing credentials. The office requires individual staff authentication, including locally. Bootstrap an administrator from private stdin as described in [Staff access](docs/staff-access.md). Use localhost or a TLS development hostname for secure cookies.

`brightwater seed` loads labelled fictional fixtures, never a real customer import. It does not enable dialing. `brightwater status` shows counts and the database control switch; `brightwater pause` stops new call admission. There is deliberately no general enable switch in the initial UI or CLI. A controlled activation/release procedure is outstanding.

## Independent shadow environment

```sh
python3 scripts/configure_local.py --environment shadow --output .env.shadow
docker compose --env-file .env.shadow --project-name brightwater-shadow -f compose.yaml -f compose.shadow.yaml up --build -d
docker compose --env-file .env.shadow --project-name brightwater-shadow -f compose.yaml -f compose.shadow.yaml run --rm api brightwater seed
```

This creates separate project volumes and credentials; the shadow network is internal and dialing is forbidden in application configuration. The supplied override is for offline QA of the business API/UI, not a LiveKit-connected runtime. Verify isolation on the target host before using copied/redacted traffic. Never replay production writes, destinations, secrets or provider callbacks into it. A read replica is not a writable shadow sandbox. A production HA standby, showcase host and disaster-recovery environment remain separate deployment work.

## Develop and verify

Backend: Python 3.12, `uv` 0.11.19; frontend: Node 24, pnpm 10.22.0. Dependencies are locked.

```sh
cd backend
uv sync --frozen --extra dev --extra voice
uv run alembic upgrade head
uv run alembic check
uv run ruff check src tests
uv run pytest -q
```

Supply private `BW_` configuration to the backend process. Tests require `BW_ENVIRONMENT=test`, an isolated PostgreSQL database whose URL contains `/brightwater_test`, distinct operator/runtime tokens of at least 32 characters, Redis and `BW_DIALING_ENABLED=false`. Tests **drop and recreate the test schema**; never point them at a useful database. `BW_TEST_ENV_FILE` optionally selects a private test configuration. Tests enforce the test-environment/name guard before resetting anything.

```sh
cd web
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

See [validation](docs/validation.md), [voice baseline](docs/voice-baseline.md), [Plivo setup](docs/plivo-livekit.md) and [remaining release work](docs/release-readiness.md). The user's existing numbers are Indian; the Plivo setup includes the required India-region verification. Running unit/integration tests does not qualify speech quality or prove the telephony provider route.

## Runtime and deployment boundaries

The API is authoritative for business actions. Redis is a broker, PostgreSQL holds recoverable intent. Provider calls happen after the durable claim and outside the database lock. A provider timeout can mean an accepted call; those intents block a new call until reviewed. Current reconciliation flags uncertainty but does not yet query authoritative carrier termination evidence.

The public candidate has TLS routing, individual database-backed staff sessions, role permissions, encrypted recording storage and an isolated backup restore check. Shared office passwords and Basic authentication are removed from the web application. Enterprise SSO/MFA, managed secret custody, continuous monitoring, scheduled off-site recovery and tested worker draining remain release work. The voice runtime requires an HTTPS business API in deployed environments. The optional SIP profile requires its own LiveKit project; the deployed roomless Plivo gateway does not.

The direct provider adapter now supports OpenAI Realtime text plus ElevenLabs TTS, or cascaded OpenAI STT/LLM plus ElevenLabs TTS, with local semantic turn detection and Silero. It requires no LiveKit Inference subscription. The original hosted inference path remains an option. Direct mode currently uses VAD interruption handling; hosted adaptive interruption classification is not claimed. ElevenLabs Agents is implemented with native business tools and an adapter to the existing Plivo stream; handset qualification remains outstanding. No provider/model is declared the voice winner. That choice depends on the real handset benchmark with voice 35%, conversation 35%, task correctness 15%, operations 10% and total cost 5%, subject to hard safety gates.

## Current deployed engineering candidate

Office: https://office.46.101.11.137.sslip.io · API readiness: https://api.46.101.11.137.sslip.io/health/ready

The approved London office host costs $24/month and the dedicated India voice host $12/month compute, before tax and voice usage. Eight labelled assessment customers and twelve prior attended engineering calls are retained. Six individual staff accounts are deployed; see [Staff access](docs/staff-access.md). Credentials are private, never in this source archive. See [deployment evidence](docs/deployment-report.md) and [current validation](docs/validation.md). The Quality view contains four actual voice audition clips; phone/conversation scores remain unmeasured.


## Direct attended India voice service

The additional approved India host now runs the direct Plivo streaming gateway and the real speech pipeline. It uses the existing business tools without LiveKit Cloud/SIP credentials. The operator-controlled attended test is separate from UK campaign calling. See [voice gateway implementation and qualification](docs/voice-gateway.md). Two-way handset speech and protected carrier recordings have been observed. Full booking, safety/privacy scenarios, latency and independent voice/conversation scoring still need qualification; synthetic audio checks are not handset quality scores.


## Selected conversation update

The owner selected **Lily with ElevenLabs v4 Turbo** after short auditions. The deployed direct engineering service uses staged identity/booking prompts and tools, bounded early LLM generation, natural-date readbacks and carrier-confirmed SDK speech-start events. The Quality page keeps matching comparisons. [Conversation evidence and limits](docs/conversation-improvement.md) records actual provider checks, the remaining endpointing delay and the next handset qualification. These changes do not grant a new call allowance or enable UK customer calling.

### Native managed voice candidate

The private ElevenLabs Agents candidate and its real booking evaluation adapter are described in [managed-voice-candidate.md](docs/managed-voice-candidate.md). Administrators can use `/managed` once configured. Its separate database prevents evaluation bookings from changing the office diary. Browser voice booking remains blocked because browser history alone cannot prove original speech/playback order. The managed Plivo engineering adapter retains the existing original-speech and carrier-playback guards; handset qualification remains outstanding. Text integration results are not telephone quality scores.

The managed path now interprets natural booking/change/cancellation intent in context and preserves original speech/playback safeguards. The twelfth handset attempt exposed a postcode/year matcher defect; fixes and real model/database evidence are in [the current managed report](docs/managed-voice-candidate.md). Calling remains paused pending fresh attended qualification.

[Native quality tuning and SIP preparation](docs/elevenlabs-quality-and-sip.md) records the deployed dictionary/keyterms, native regression suite, selective tool acknowledgements, split-ASR timing repair, measured probe limits and inactive imported number. The working bridge remains in service; direct SIP is not yet qualified for business writes.


Current contextual language implementation and measured scope: [dynamic conversations](docs/dynamic-conversation.md). Speech stays on ElevenLabs; independent business interpretation now uses GPT-4.1. Calling remains paused pending fresh attended qualification.


Latest actual phone result and pause changes: [call15 booking and pause reduction](docs/call15-booking-and-pause-reduction.md). One engineering booking succeeded; updated handset latency remains unmeasured.

Latest investigation: [call16 service disconnect](docs/call16-service-disconnect.md).

Latest test: [call17 result](docs/call17-test-result.md).

Playback receipt repair and remaining qualification: [sequence repair](docs/playback-ack-sequence-repair.md).

Attended phone tests now allow up to two hours after the owner removed the three-minute cutoff. Calling remains paused; no additional attempt is authorised. See [current duration and retained call results](docs/attended-test-duration.md).

````
