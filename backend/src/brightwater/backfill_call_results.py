"""Repair historical telephone results without placing calls or scheduling retries."""
import argparse
from collections import Counter

from sqlalchemy import select

from brightwater import models as m
from brightwater.call_results import NON_PHONE, refresh_result
from brightwater.config import settings
from brightwater.db import session
from brightwater.policy import now
from brightwater.services import ACTIVE, control_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist changes; otherwise roll back")
    args = parser.parse_args()
    if settings().dialing_enabled:
        raise RuntimeError("Pause the campaign before updating historical results")
    counts = Counter()
    with session() as db:
        control_lock(db)
        if db.scalar(select(m.Call.id).where(m.Call.state.in_(ACTIVE)).limit(1)):
            raise RuntimeError("Resolve any active or uncertain calls before updating historical results")
        calls = db.scalars(select(m.Call).where(m.Call.purpose.not_in(NON_PHONE),
            m.Call.state.in_(["finished", "failed"])).order_by(m.Call.id).with_for_update()).all()
        for call in calls:
            events = list(db.scalars(select(m.CallEvent).where(m.CallEvent.call_id == call.id)))
            old = (call.outcome, call.summary, call.outcome_review_required)
            refresh_result(db, call, events, historical=True)
            counts["review_required"] += int(call.outcome_review_required)
            if old == (call.outcome, call.summary, call.outcome_review_required):
                continue
            counts["updated"] += 1
            counts["outcomes_filled"] += int(old[0] is None)
            key = "historical-call-results-v1"
            if not any(e.provider_event_id == key for e in events):
                db.add(m.CallEvent(call_id=call.id, provider_event_id=key, kind="call_result_backfilled",
                    occurred_at=now(), payload={"previous_outcome": old[0], "new_outcome": call.outcome,
                                               "technical_review": call.outcome_review_required}))
        db.commit() if args.apply else db.rollback()
    print("Applied" if args.apply else "Dry run", dict(counts))


if __name__ == "__main__":
    main()
