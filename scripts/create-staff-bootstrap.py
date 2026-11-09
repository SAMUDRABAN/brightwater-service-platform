"""Create private, unique local staff credentials. Never resets a deployed user."""
import argparse
import json
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.output.expanduser().resolve()
if output == root or root in output.parents:
    raise SystemExit("Keep staff credentials outside the repository")
if output.exists():
    raise SystemExit("Refusing to overwrite an existing credential file")
people = [
    ("mark", "Mark Ellis", "admin", None),
    ("sarah", "Sarah Collins", "office", None),
    ("dan", "Dan Hughes", "engineer", "dan"),
    ("priya", "Priya Shah", "engineer", "priya"),
    ("tom", "Tom Barker", "engineer", "tom"),
    ("samudra", "Samudra Banerjee", "admin", None),
]
records = [{"username": u, "name": n, "role": r, "engineer_id": e,
            "temporary_password": secrets.token_urlsafe(28)} for u, n, r, e in people]
output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
    json.dump(records, file, indent=2)
    file.write("\n")
print("Private bootstrap file created. Read it locally; do not commit or share it in a repository.")
