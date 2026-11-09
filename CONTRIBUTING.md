# Contributing

Use Python 3.12, Node.js 24, uv 0.11.19 and pnpm 10.22.0. Install from the checked-in lockfiles. Do not commit credentials, caller recordings, database exports or runtime state.

## Check a change

```sh
python scripts/check-version.py
cd backend
uv sync --frozen --extra dev --extra voice
uv run ruff check src tests
# BW_TEST_ENV_FILE must identify an isolated test database containing /brightwater_test.
uv run pytest -q
cd ../web
pnpm install --frozen-lockfile
pnpm format:check
pnpm test
pnpm build
```

Backend tests reset their guarded test database. Never point them at a useful environment. Native voice/provider evaluations are separately invoked, paid engineering checks; the regular test suite must not dial or require production credentials.

## Change and release conventions

- Use a descriptive branch, for example `feat/office-follow-ups` or `fix/customer-preferences`.
- Use Conventional Commit-style subjects: `feat(crm): ...`, `fix(auth): ...`, `docs: ...`.
- Use Python `snake_case`; TypeScript `camelCase`; React component and type names `PascalCase`; route folders and documentation filenames `kebab-case`. Preserve stable customer IDs and external API contracts.
- `VERSION`, `backend/pyproject.toml`, `backend/uv.lock` and `web/package.json` must agree. `scripts/check-version.py` checks the release metadata. Git tags use `vX.Y.Z`.
- Explain behaviour, permissions, tests and outstanding qualification in the change description. Prefer focused changes over large unrelated renames.
- Record schema changes as forward Alembic migrations with a tested recovery path. This CRM release adds no schema migration; office notes use immutable call events and the existing follow-up state.
- Review role boundaries, calling consent, suppression, UK local-time behaviour, idempotency, capacity and failure recovery. Do not loosen these to produce a successful demonstration.

See [engineering conventions](docs/engineering-conventions.md), [design](DESIGN.md) and [assessment coverage](docs/submission/assessment-coverage.md).
