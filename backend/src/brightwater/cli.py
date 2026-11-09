import argparse
import json

from sqlalchemy import select

from brightwater import models as m
from brightwater.db import session
from brightwater.seed import seed


def main():
    parser = argparse.ArgumentParser(description="Brightwater operator tools")
    parser.add_argument("command", choices=["seed", "status", "pause"])
    args = parser.parse_args()
    with session() as db, db.begin():
        if args.command == "seed":
            print("Assessment fixture loaded" if seed(db) else "Data already present; no changes")
        elif args.command == "pause":
            control = db.get(m.Control, "dialing")
            if control:
                control.enabled = False
            print("New calls paused")
        else:
            print(json.dumps({"customers": len(db.scalars(select(m.Customer)).all()),
                              "calls": len(db.scalars(select(m.Call)).all()),
                              "dialing_control": bool(db.get(m.Control, "dialing") and db.get(m.Control, "dialing").enabled)}))
