"""One-time operator bootstrap. Read JSON from private stdin, never CLI arguments.

Each item supplies username, name, role, optional engineer_id and temporary_password.
Existing identities are left unchanged; use the authenticated team screen for resets.
"""
import json
import re
import sys

from brightwater import models as m
from brightwater.db import session
from brightwater.staff import audit, password_hash


def main():
    if sys.stdin.isatty():
        raise SystemExit("Pipe a private JSON file to stdin; do not enter credentials in shell arguments")
    accounts = json.load(sys.stdin)
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 100:
        raise SystemExit("Expected a bounded account list")
    with session() as db, db.begin():
        created = 0
        for account in accounts:
            username, role = account["username"], account["role"]
            password = account["temporary_password"]
            engineer = account.get("engineer_id")
            if not re.fullmatch(r"[a-z0-9_-]{1,80}", username) or role not in ("admin", "office", "engineer"):
                raise SystemExit("Invalid account or role")
            if not 14 <= len(password) <= 128 or not 1 <= len(account["name"]) <= 100:
                raise SystemExit("Invalid password or name length")
            if role == "engineer" and (not engineer or not db.get(m.Engineer, engineer)):
                raise SystemExit("Engineer requires an existing diary identity")
            if db.get(m.StaffUser, username):
                continue
            db.add(m.StaffUser(username=username, name=account["name"], role=role, engineer_id=engineer,
                               password_hash=password_hash(password), change_required=True))
            audit(db, username, "account_bootstrapped")
            created += 1
    print(f"Staff bootstrap completed: {created} created; existing accounts unchanged")


if __name__ == "__main__":
    main()
