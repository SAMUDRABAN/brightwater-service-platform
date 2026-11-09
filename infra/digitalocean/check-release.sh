#!/usr/bin/env bash
# Temporary internal Docker network/DB. Never connects tests to candidate data.
set -euo pipefail
cd "$(dirname "$0")/../.."
run_id=brightwater-verify-$(date +%s)
private_dir=$(mktemp -d)
chmod 0700 "$private_dir"
cleanup() {
  docker rm -f "$run_id-postgres" "$run_id-redis" >/dev/null 2>&1 || true
  docker network rm "$run_id" >/dev/null 2>&1 || true
  rm -rf "$private_dir"
}
trap cleanup EXIT
python3 - "$private_dir/test.env" <<'PY'
import os, secrets, sys
password = secrets.token_urlsafe(32)
values = {
    'POSTGRES_USER': 'brightwater_test', 'POSTGRES_PASSWORD': password,
    'POSTGRES_DB': 'brightwater_test', 'BW_ENVIRONMENT': 'test',
    'BW_DATABASE_URL': f'postgresql+psycopg://brightwater_test:{password}@postgres:5432/brightwater_test',
    'BW_REDIS_URL': 'redis://redis:6379/0', 'BW_DIALING_ENABLED': 'false',
    'BW_OPERATOR_TOKEN': secrets.token_urlsafe(40), 'BW_RUNTIME_TOKEN': secrets.token_urlsafe(40),
}
with os.fdopen(os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
    output.write('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
PY
# Test files are intentionally excluded from the production build context;
# a temporary checks-specific context includes only reviewed source files.
context=$private_dir/context
mkdir "$context"
cp backend/pyproject.toml backend/uv.lock backend/alembic.ini "$context/"
cp backend/Dockerfile.checks "$context/Dockerfile"
cp -R backend/src backend/tests backend/migrations "$context/"
docker build -t brightwater-checks:latest "$context"
docker network create --internal "$run_id" >/dev/null
docker run -d --name "$run_id-postgres" --network "$run_id" --network-alias postgres --env-file "$private_dir/test.env" postgres:17 >/dev/null
docker run -d --name "$run_id-redis" --network "$run_id" --network-alias redis redis:7.4 >/dev/null
ready=false
for attempt in $(seq 1 30); do
  if docker exec "$run_id-postgres" pg_isready -U brightwater_test -d brightwater_test >/dev/null; then ready=true; break; fi
  sleep 1
done
[[ $ready == true ]] || { echo 'Isolated test PostgreSQL did not become ready.' >&2; exit 1; }
docker run --rm --network "$run_id" --env-file "$private_dir/test.env" brightwater-checks:latest
# Remove only the temporary, reviewed source context after the runner exits.
rm -rf "$context"
