"""Create private nondialling deployment configuration; never print credentials."""
import argparse
import base64
import os
import re
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--environment", choices=["production", "shadow"], required=True)
parser.add_argument("--web-host", required=True)
parser.add_argument("--api-host", required=True)
parser.add_argument("--tls-email", required=True)
parser.add_argument("--release-id", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
output = args.output.expanduser().resolve()
if output == repo or repo in output.parents:
    raise SystemExit("Write credentials outside the repository, e.g. private work/runtime.")
for host in (args.web_host, args.api_host):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host:
        raise SystemExit("Hosts must be lowercase DNS names without schemes/paths.")
if args.web_host == args.api_host:
    raise SystemExit("Use distinct office and API hostnames.")
if not re.fullmatch(r"[^\s=]+@[^\s=]+\.[^\s=]+", args.tls_email):
    raise SystemExit("Supply a valid certificate-contact email.")
if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", args.release_id):
    raise SystemExit("Invalid release identifier.")
output.parent.mkdir(parents=True, exist_ok=True)
db_password, redis_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
env = args.environment
values = {
    "BW_ENVIRONMENT": env, "BW_STACK_NAME": f"brightwater-{env}",
    "POSTGRES_USER": "brightwater", "POSTGRES_PASSWORD": db_password,
    "POSTGRES_DB": f"brightwater_{env}", "REDIS_PASSWORD": redis_password,
    "BW_DATABASE_URL": f"postgresql+psycopg://brightwater:{db_password}@db:5432/brightwater_{env}",
    "BW_REDIS_URL": f"redis://:{redis_password}@redis:6379/0",
    "BW_OPERATOR_TOKEN": secrets.token_urlsafe(40),
    "BW_RUNTIME_TOKEN": secrets.token_urlsafe(40),
    "BW_DIALING_ENABLED": "false",
    "BW_MEDIA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), "BW_RELEASE_ID": args.release_id,
    "BW_API_URL": f"https://{args.api_host}",
    "BW_WEB_HOST": args.web_host, "BW_API_HOST": args.api_host,
    "BW_TLS_EMAIL": args.tls_email,
    "BW_LIVEKIT_URL": "", "BW_LIVEKIT_API_KEY": "", "BW_LIVEKIT_API_SECRET": "",
    "BW_LIVEKIT_OUTBOUND_TRUNK_ID": "", "BW_VOICE_AGENT_NAME": f"brightwater-{env}",
    "BW_VOICE_STT_MODEL": "", "BW_VOICE_LLM_MODEL": "", "BW_VOICE_TTS_MODEL": "",
    "BW_VOICE_ID": "", "BW_RECORDING_NOTICE": "",
}
if any("\n" in value or "\r" in value for value in values.values()):
    raise SystemExit("Configuration cannot contain newlines.")
with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
    target.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
print(f"Created private {env} configuration at {output}; dialing remains disabled.")
