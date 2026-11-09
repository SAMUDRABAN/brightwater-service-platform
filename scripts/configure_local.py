"""Generate private local/QA credentials; no infrastructure or calls are created."""
import argparse
import base64
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--environment", choices=["local", "shadow", "showcase"], default="local")
parser.add_argument("--output", type=Path, default=Path(".env"))
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Refusing to overwrite an existing credential file")
db_password, redis_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
values = {
    "BW_ENVIRONMENT": args.environment, "BW_STACK_NAME": f"brightwater-{args.environment}",
    "POSTGRES_USER": "brightwater", "POSTGRES_PASSWORD": db_password,
    "POSTGRES_DB": f"brightwater_{args.environment}", "REDIS_PASSWORD": redis_password,
    "BW_DATABASE_URL": f"postgresql+psycopg://brightwater:{db_password}@db:5432/brightwater_{args.environment}",
    "BW_REDIS_URL": f"redis://:{redis_password}@redis:6379/0",
    "BW_OPERATOR_TOKEN": secrets.token_urlsafe(40), "BW_RUNTIME_TOKEN": secrets.token_urlsafe(40),
    "BW_DIALING_ENABLED": "false", "BW_RELEASE_ID": "development",
    "BW_MEDIA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "BW_API_URL": "http://api:8787" if args.environment == "local" else "https://shadow.invalid",
    "BW_WEB_PORT": "3000" if args.environment == "local" else "3001",
    "BW_API_PORT": "8787" if args.environment == "local" else "8788",
}
with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
    target.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
print(f"Private {args.environment} configuration created at {args.output}. Dialing is disabled.")
