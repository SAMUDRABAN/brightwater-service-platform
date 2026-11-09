#!/usr/bin/env bash
# Run only on a newly approved Ubuntu 24.04 host. No DigitalOcean API mutation.
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo 'Run as root on the approved new host.' >&2; exit 1; fi
if [[ ${1:-} != --new-brightwater-host ]]; then echo 'Expected --new-brightwater-host.' >&2; exit 1; fi
source /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 24.04 ]]; then echo 'Ubuntu 24.04 is required.' >&2; exit 1; fi
if [[ -e /opt/brightwater/current || -e /etc/brightwater/environment ]]; then
  echo 'Existing Brightwater installation found; use the deployment runbook.' >&2; exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssh-server
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
arch=$(dpkg --print-architecture)
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$arch" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
install -d -m 0700 /etc/brightwater
install -d -m 0750 /opt/brightwater/releases /var/backups/brightwater
printf '%s\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' 'PermitRootLogin prohibit-password' > /etc/ssh/sshd_config.d/60-brightwater.conf
install -d -m 0755 /run/sshd
sshd -t
systemctl reload ssh
# Docker published-port exposure must be controlled by the DO Cloud Firewall.
# Do not rely on UFW alone: Docker can bypass ordinary host firewall rules.
echo 'Host software installed. Verify Cloud Firewall and host key before deployment.'
