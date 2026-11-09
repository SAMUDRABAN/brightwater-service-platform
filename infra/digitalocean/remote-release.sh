#!/usr/bin/env bash
# Called by deploy-existing-host.sh after uploading a reviewed committed release.
set -euo pipefail
environment=${1:?environment required}
commit=${2:?commit required}
[[ $environment == production || $environment == shadow ]] || exit 1
[[ $commit =~ ^[a-f0-9]{40}$ ]] || exit 1
release=/opt/brightwater/releases/$commit
cd "$release"
python3 - "$environment" /etc/brightwater/environment.next <<'PY'
import sys
from pathlib import Path
target, file = sys.argv[1:]
values = dict(line.split("=", 1) for line in Path(file).read_text().splitlines() if line and not line.startswith("#"))
if values.get("BW_ENVIRONMENT") != target or values.get("BW_DIALING_ENABLED") != "false":
    raise SystemExit("Environment mismatch or dialing enabled; deployment refused.")
if not values.get("BW_API_URL", "").startswith("https://"):
    raise SystemExit("HTTPS runtime API URL required.")
if target == "shadow" and any(values.get(k) for k in ("BW_LIVEKIT_API_KEY", "BW_LIVEKIT_API_SECRET", "BW_LIVEKIT_OUTBOUND_TRUNK_ID", "BW_OPENAI_API_KEY", "BW_ELEVENLABS_API_KEY")):
    raise SystemExit("Provider credentials are forbidden in shadow.")
PY
if [[ -f /etc/brightwater/environment ]]; then
  old_environment=$(sed -n 's/^BW_ENVIRONMENT=//p' /etc/brightwater/environment)
  [[ $old_environment == "$environment" ]] || { echo 'Host environment cannot be changed in place.' >&2; exit 1; }
  # Reusing the data volumes requires exactly the existing DB/Redis passwords.
  python3 - <<'PY'
from pathlib import Path
def read(p): return dict(x.split("=", 1) for x in Path(p).read_text().splitlines() if x and not x.startswith("#"))
a, b = read('/etc/brightwater/environment'), read('/etc/brightwater/environment.next')
for key in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'REDIS_PASSWORD', 'BW_MEDIA_ENCRYPTION_KEY'):
    if a.get(key) != b.get(key): raise SystemExit('Existing data credentials changed; use an explicit rotation procedure.')
PY
fi
compose_version=$(docker compose version --short | sed 's/^v//')
[[ $(printf '%s\n' 2.24.4 "$compose_version" | sort -V | head -n1) == 2.24.4 ]] || { echo 'Compose >=2.24.4 required.' >&2; exit 1; }
install -m 0600 /etc/brightwater/environment.next /etc/brightwater/environment
rm /etc/brightwater/environment.next
project=brightwater-$environment
options=(--env-file /etc/brightwater/environment --project-name "$project" -f compose.yaml -f infra/digitalocean/compose.yaml)
if [[ $environment == shadow ]]; then options+=(-f infra/digitalocean/compose.qa.yaml); fi
export COMPOSE_PARALLEL_LIMIT=1
# Never print docker compose config: resolved output contains secrets.
docker compose "${options[@]}" config --quiet
docker compose "${options[@]}" build
# No voice profile here; media service activation is a separate reviewed change.
docker compose "${options[@]}" stop beat worker
docker compose "${options[@]}" up -d --wait --wait-timeout 240
docker compose "${options[@]}" exec -T api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8787/health/ready", timeout=10).read(); print("API database/broker readiness passed")'
ln -sfn "$release" /opt/brightwater/current
printf 'Release %s running as %s; no fixtures loaded and dialing disabled. Verify HTTPS externally.\n' "$commit" "$environment"
