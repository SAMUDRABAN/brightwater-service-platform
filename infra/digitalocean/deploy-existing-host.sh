#!/usr/bin/env bash
# Upload a committed release/config to one APPROVED existing new host, then run it.
# Never creates Droplets, numbers, firewalls, DNS or provider resources.
set -euo pipefail
if [[ $# -ne 4 ]]; then
  echo 'Usage: deploy-existing-host.sh root@HOST PRIVATE_ENV production|shadow COMMIT' >&2; exit 1
fi
target=$1
envfile=$2
environment=$3
revision=$4
[[ $target =~ ^root@[a-zA-Z0-9.-]+$ ]] || { echo 'Expected root@HOST.' >&2; exit 1; }
[[ $environment == production || $environment == shadow ]] || exit 1
[[ -f $envfile ]] || { echo 'Private environment file missing.' >&2; exit 1; }
repo=$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)
commit=$(git -C "$repo" rev-parse --verify "$revision^{commit}")
git -C "$repo" cat-file -e "$commit:infra/digitalocean/remote-release.sh"
# Only a committed source archive is shipped. Untracked credentials cannot enter it.
ssh_flags=(-o BatchMode=yes -o StrictHostKeyChecking=yes)
if [[ -n ${BW_SSH_IDENTITY_FILE:-} ]]; then ssh_flags+=(-i "$BW_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes); fi
if [[ -n ${BW_SSH_KNOWN_HOSTS_FILE:-} ]]; then ssh_flags+=(-o "UserKnownHostsFile=$BW_SSH_KNOWN_HOSTS_FILE"); fi
ssh "${ssh_flags[@]}" "$target" 'install -d -m 0700 /etc/brightwater; install -d -m 0750 /opt/brightwater/releases'
git -C "$repo" archive "$commit" | ssh "${ssh_flags[@]}" "$target" "install -d -m 0750 /opt/brightwater/releases/$commit; tar -xf - -C /opt/brightwater/releases/$commit"
# Secrets travel via the encrypted SSH stream, never shell arguments/logged stdout.
ssh "${ssh_flags[@]}" "$target" 'umask 077; cat > /etc/brightwater/environment.next' < "$envfile"
ssh "${ssh_flags[@]}" "$target" "bash /opt/brightwater/releases/$commit/infra/digitalocean/remote-release.sh $environment $commit"
