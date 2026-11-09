# DigitalOcean deployment runbook

Updated 6 November 2026. The root agent deployed commit `05244fa1437dd2f5a4e113fe9b1a84cac4e4807f` to one approved London host. Docker builds, public TLS and an isolated 61-test PostgreSQL 17 suite passed there. See [actual deployment evidence](deployment-report.md). This runbook also describes future QA topology; it is not evidence that a second host exists.

## Scope and account constraints

The read-only account inventory reported a limit of three Droplets and one pre-existing active `s-2vcpu-4gb` Droplet in `blr1` (ID `615100245`). **Do not modify, reboot, resize, relabel, firewall or destroy that existing machine.** Two new machines fit the reported quota, subject to a fresh account check immediately before provisioning.

Use `lon1` (London) for the UK business/control plane. The user approved **one $24/month host initially**. A separately provisioned QA host is future work and requires additional budget authorisation. This choice does not establish where Indian-number SIP media must run. No voice media service is activated by these scripts. Plivo/Zentrunk/LiveKit route provisioning, India-region restrictions, UK test destinations and call permissions remain separate work.

Topology (only the first host was provisioned):

- New `brightwater-production-candidate` host: Docker Compose API, office UI, PostgreSQL, Redis, Celery worker, one fenced Beat and TLS proxy. Dialing disabled, no sample fixtures automatically loaded.
- New `brightwater-qa` host: same application image/source with separate PostgreSQL and Redis volumes, passwords/tokens, hostnames and TLS state. Application mode `shadow`, no telephony credentials, worker/Beat/voice networks have no Internet egress. It is a writable QA database, not a read replica or HA standby.
- Only Caddy publishes ports 80/443. No database, Redis, API port 8787 or UI port 3000 is published, even on loopback. The API is reached through its TLS hostname, with application authorization intact; metrics are blocked at the public proxy.

The production candidate remains a **single-host failure domain**, with self-managed DB/broker and no automatic host failover. Two hosts assigned to different environments do not provide production HA. Real customer calling requires the release/restore/media/security gates below; an Internet URL does not mean the system is enterprise-qualified.

## Verified compute estimate

Read-only official `GET https://api.digitalocean.com/v2/sizes?per_page=200` at 2026-11-05 18:43:53 UTC returned these available `lon1` bundled sizes. The selected observations are saved without account credentials in `infra/digitalocean/cost-observation.json`.

| Size | RAM/vCPU | Hourly USD | Monthly USD |
|---|---|---:|---:|
| `s-2vcpu-2gb` | 2 GiB / 2 | 0.02679 | 18 |
| `s-2vcpu-4gb` | 4 GiB / 2 | 0.03571 | 24 |
| `s-4vcpu-8gb` | 8 GiB / 4 | 0.07143 | 48 |

**Approved and deployed: one 4-GiB host = $24/month incremental compute**, or $0.03571/hour at returned rates. The earlier two-host $48/month proposal was not approved. Four GiB provides more room for the initial backend/frontend image builds than the cheaper 2-GiB size; it is a starting allocation, not a load-test result. Do not size a production voice-worker pool from this control-plane allocation.

Official backup pricing lists weekly basic backups at 20% of Droplet monthly cost and daily basic backups at 30%. Both $24 hosts with weekly basic backup would add $9.60/month ($57.60 compute + basic backups); daily adds $14.40 ($62.40 total). These are optional plan illustrations, **not enabled resources**. Usage-based backup plans have different GiB billing. Cloud Firewalls are documented as no-additional-cost. Taxes, snapshots, off-host DB backup storage, domains, managed databases, load balancers, excess transfer and all telephony/media/inference costs are excluded. Existing Droplet cost is excluded. Refresh availability/rates before creation. [Droplet creation/size API](https://docs.digitalocean.com/products/droplets/how-to/create/), [backup pricing](https://docs.digitalocean.com/products/backups/details/pricing/), [Cloud Firewall rules](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/).

## Provisioning checklist for the root agent

1. Recheck quota/inventory and the selected size/image availability. Create **only new** resources in London, using Ubuntu 24.04, the user's approved SSH public key and clear Brightwater-specific names/tags. Record new IDs, public IPs and chosen backup options privately. No DigitalOcean token belongs on these hosts.
2. Use a dedicated project/VPC if practical. A VPC is connectivity isolation, not an automatic deny policy. Do not give QA credentials or network permissions to production data services. The supplied initial stack requires no cross-host database connection. [VPC](https://docs.digitalocean.com/products/networking/vpc/).
3. Review `infra/digitalocean/firewall.example.json`, replace the administrator CIDR and set **only the new host's ID**. Create/attach separate Cloud Firewalls. Public 80/443 support ACME and HTTPS; SSH is administrator-CIDR-only. No ports 5432/6379/8787/3000. The example is a template, not an executed API command. Its egress supports control-plane HTTPS/package downloads, DNS and time; it intentionally does not allow SIP/RTP media. IPv6 is not included: either leave IPv6 disabled or create equivalent reviewed IPv6 rules before publishing AAAA records. Do not assume UFW blocks Docker-published ports. [DO firewall](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/), [Docker firewall warning](https://docs.docker.com/engine/install/ubuntu/).
4. Establish and verify each SSH host key through an independently trusted channel before adding it to `known_hosts`; never use `StrictHostKeyChecking=no`. Confirm target identity, London region and no existing user workload.
5. Copy/run `infra/digitalocean/bootstrap-host.sh --new-brightwater-host` on each newly approved Ubuntu host. It installs Docker from the signed official repository, requires key-only SSH and creates private deployment directories. It does not create a firewall, domain or Droplet. [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/).
6. Configure four distinct DNS names: production office/API and QA office/API. Point A records at their corresponding new host. Do not publish an unconfigured AAAA. If root chooses a temporary IP-derived hostname, verify its DNS/control/trust limitations and treat it as temporary; the scripts do not assume ownership of Brightwater's fictional domain.

## Prepare independent secrets and deploy

Commit reviewed source and infrastructure changes first. The deploy script ships `git archive` of the requested commit, so it cannot accidentally upload untracked API keys, `.env`, runtime database files or local artifacts. The private environment generator refuses to write inside the repository and refuses to overwrite a file. No cloud/provider credentials are loaded by it.

From repository root, use your actual approved hostnames/email and an absolute private path outside the repository:

```sh
REV=$(git rev-parse HEAD)
python3 infra/digitalocean/configure.py --environment production \
  --web-host OFFICE_HOST --api-host API_HOST --tls-email CERTIFICATE_CONTACT_EMAIL \
  --release-id "$REV" --output /ABSOLUTE/PRIVATE/production.env
python3 infra/digitalocean/configure.py --environment shadow \
  --web-host QA_OFFICE_HOST --api-host QA_API_HOST --tls-email CERTIFICATE_CONTACT_EMAIL \
  --release-id "$REV" --output /ABSOLUTE/PRIVATE/qa.env

bash infra/digitalocean/deploy-existing-host.sh root@APPROVED_NEW_PRODUCTION_IP \
  /ABSOLUTE/PRIVATE/production.env production "$REV"
bash infra/digitalocean/deploy-existing-host.sh root@APPROVED_NEW_QA_IP \
  /ABSOLUTE/PRIVATE/qa.env shadow "$REV"
```

The placeholders are intentionally not working credentials/targets. Private files are mode 0600. Upload uses SSH stdin; passwords/tokens are not placed in SSH arguments. On each host, `/etc/brightwater/environment` is root-only. Runtime environment values are visible to host root/Docker administrators; this is not a managed secret-store integration. Keep all private files out of the repository and user-facing outputs. Never run a shell with `set -x`, print the environment, or capture expanded `docker compose config` in logs.

The script validates the environment/dialing state, requires Compose >=2.24.4 for `!override`, builds serially, stops worker/Beat for the migration/restart, applies migrations, starts actual services and checks DB/broker/API readiness. It does not enable the voice profile, load fixtures or enable dialing. Existing volume credentials cannot be silently changed during redeployment. The active source symlink is `/opt/brightwater/current`; persistent Docker volumes are keyed by environment's Compose project name, not the source SHA.

For subsequent releases, reuse the existing private environment file with its existing DB/Redis passwords and update only the reviewed release marker/configuration. Do not generate a fresh file over an existing data volume. Secret rotation needs coordinated PostgreSQL/Redis changes. This script offers maintenance-window deployment; it is not blue/green or zero-downtime. Schema changes must be backward compatible or have a planned outage/restore strategy.

Caddy obtains and renews public certificates, stores state in persistent volumes and redirects HTTP to HTTPS. DNS must resolve correctly and public challenge ports must be reachable. A running Caddy container is not proof that a certificate was issued. [Automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).

## Acceptance checks on the actual hosts

Run these before reporting deployment complete:

- External `https://API_HOST/health/ready` returns the expected environment with `dialing_enabled=false`; hostname/certificate valid, no `--insecure`. Repeat independently for QA.
- Unauthenticated `https://OFFICE_HOST/morning` redirects to the login form; an authorized browser session shows the actual backend environment/release and actual database counts. Do not print credentials in commands/tool logs; a user's private login handoff is separate from providing public links.
- Unauthenticated API operator/runtime endpoints return 401; `https://API_HOST/metrics` returns 404 from the proxy. Public probes cannot reach 5432, 6379, 8787 or 3000. A local port listing alone is not external firewall evidence.
- QA database/Redis credentials and Docker volume IDs differ; QA cannot reach provider endpoints from API/worker/Beat/voice containers. Inspect actual container networks, not only the YAML. Caddy alone has Internet egress for ACME. No LiveKit key/trunk exists in QA settings.
- Worker and Beat logs show healthy queue consumers and one scheduler owner. Test a second Beat in QA and require the database leadership lock to reject it. Broker restart and worker restart in QA must preserve durable PostgreSQL intents without duplicate external requests.
- Restart the QA host/containers and verify durable records survive. Test a failed migration/build without corrupting the active data. Keep database migration output internal; it may contain operational details.
- A QA-only `brightwater seed` command may load labelled fictional assessment records. Do not present these as real production activity, and do not import them automatically to production. The running application is real even when its assessment data is explicitly fictional.
- Capture successful HTTPS/access/network/container/worker checks and the deployed source SHA. Mark phone/media recording, restore, SSO and HA checks outstanding until actually performed.

## Backups, rollback and qualification boundaries

`infra/digitalocean/backup-db.sh production` creates a consistent PostgreSQL custom-format logical backup in root-only `/var/backups/brightwater` with a checksum. Run through the approved host context. The file stays on the same host and is **not yet disaster recovery**. Copy it encrypted to separately controlled off-host storage, set retention and alerting, and restore it to a freshly isolated QA database before claiming a verified backup. Do not run destructive test-schema tests against a useful database. Never restore production destinations/credentials into a QA environment capable of dialing.

DO disk backups complement database backups; neither container AOF nor an on-host dump provides cross-host HA or PostgreSQL PITR. Redis AOF is enabled in the base stack and uses `noeviction`; PostgreSQL's outbox remains authoritative. Redis loss can require broker reconstruction/reconciliation. Do not promise zero RPO or exactly-once external phone effects.

Application rollback selects the prior committed source plus the same environment/volumes and redeploys it only if compatible with the current schema. Never automatically reverse a migration or restore an old DB while live calls may exist. Back up first, pause admission and preserve uncertain external-call state. Voice deployment must later drain existing sessions before process termination; `stop_grace_period: 30m` is a bound, not a proof of uninterrupted calls.

Before real-customer/enterprise sign-off: approved UK/India media route and real handset tests; actual recording storage/export; SSO/MFA/role policy beyond the current signed-cookie login and Basic automation fallback; external monitoring/alerts; off-host backup/restore drills and agreed RPO/RTO; release gates and incident ownership; managed/replicated production database and broker or a consciously accepted documented single-host availability policy; real CRM/calendar integration; billing/consent/privacy review. Increasing the provider quota and introducing a second production failure domain may be necessary. This runbook creates a credible initial deployment path without calling a single-host stack enterprise-ready.

## Files and checks from this lane

New files only under `infra/digitalocean/` and this runbook. No changes to existing application files. Static Bash syntax, Python compilation/configuration generation, JSON parsing and YAML/tag structure can be checked locally. Docker image construction, Compose's effective model, Caddy issuance, remote firewall/backup and runtime behavior require actual Docker/host validation and must not be described as passed from static checks.
