#!/usr/bin/env bash
# Creates a consistent logical backup, NOT a complete off-host backup system/PITR.
set -euo pipefail
umask 077
environment=${1:?Pass production or shadow}
[[ $environment == production || $environment == shadow ]] || exit 1
cd /opt/brightwater/current
options=(--env-file /etc/brightwater/environment --project-name "brightwater-$environment" -f compose.yaml -f infra/digitalocean/compose.yaml)
if [[ $environment == shadow ]]; then options+=(-f infra/digitalocean/compose.qa.yaml); fi
directory=/var/backups/brightwater
install -d -m 0700 "$directory"
destination="$directory/$environment-$(date -u +%Y%m%dT%H%M%SZ).dump"
[[ ! -e $destination && ! -e $destination.part ]] || { echo 'Backup filename collision.' >&2; exit 1; }
docker compose "${options[@]}" exec -T db sh -c 'exec pg_dump -Fc --no-owner --no-acl --username "$POSTGRES_USER" "$POSTGRES_DB"' > "$destination.part"
test -s "$destination.part"
mv "$destination.part" "$destination"
sha256sum "$destination" > "$destination.sha256"
printf 'Logical backup written privately to %s. Copy encrypted off-host and test restore.\n' "$destination"
