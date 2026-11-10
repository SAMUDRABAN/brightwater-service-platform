import asyncio
import hashlib
import secrets
from datetime import timedelta

from celery import Celery
from celery.beat import PersistentScheduler, Service
from celery.schedules import crontab
from sqlalchemy import func, or_, select, text

from brightwater import models as m
from brightwater import services as svc
from brightwater.config import settings
from brightwater.db import session
from brightwater.policy import Rejected, now
from brightwater.providers import initiate

cfg = settings()
celery = Celery("brightwater", broker=cfg.redis_url.get_secret_value())
celery.conf.update(
    timezone="Europe/London", enable_utc=True,
    task_serializer="json", accept_content=["json"], result_serializer="json",
    task_ignore_result=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 120, "global_keyprefix": f"bw:{cfg.environment}:"},
    task_soft_time_limit=30, task_time_limit=40,
    task_routes={"brightwater.dispatch": {"queue": "calls.dispatch"},
                 "brightwater.tick": {"queue": "maintenance"},
                 "brightwater.reconcile": {"queue": "calls.reconcile"}},
    beat_schedule={
        "due-and-outbox": {"task": "brightwater.tick", "schedule": 15.0},
        "unknown-review": {"task": "brightwater.reconcile", "schedule": 30.0},
        "morning-preparation": {"task": "brightwater.reconcile", "schedule": crontab(hour=8, minute=20)},
    },
)


@celery.task(name="brightwater.tick", acks_late=True)
def tick():
    # PostgreSQL is the durable job source; a broker restart cannot erase intent.
    with session() as db, db.begin():
        at = now()
        control = db.get(m.Control, "dialing")
        if cfg.dialing_enabled and control and control.enabled:
            from brightwater.campaign import configuration_issues, enqueue_due
            if not configuration_issues(cfg):
                enqueue_due(db, at)
        rows = db.scalars(select(m.Outbox).where(m.Outbox.delivered_at.is_(None),
            or_(m.Outbox.published_at.is_(None), m.Outbox.published_at < at - timedelta(seconds=60))
        ).order_by(m.Outbox.created_at).with_for_update(skip_locked=True).limit(50)).all()
        for event in rows:
            if event.topic == "calls.dispatch":
                # Publish within this transaction: if commit fails, a duplicate
                # message is safe because dispatch claims the authoritative row.
                celery.send_task("brightwater.dispatch", args=[event.id], queue="calls.dispatch")
                event.published_at = at


@celery.task(name="brightwater.dispatch", acks_late=True)
def dispatch(outbox_id):
    token = secrets.token_urlsafe(40)
    with session() as db, db.begin():
        svc.control_lock(db)
        event = db.scalar(select(m.Outbox).where(m.Outbox.id == outbox_id).with_for_update())
        if not event or event.delivered_at:
            return
        call = db.scalar(select(m.Call).where(m.Call.id == event.aggregate_id).with_for_update())
        if call.state != "queued":
            event.delivered_at = now()
            return
        control = db.get(m.Control, "dialing")
        try:
            if not cfg.dialing_enabled or not control or not control.enabled:
                raise Rejected("dialing_disabled", "New calls are paused or the provider is not configured")
            active = db.scalar(select(func.count()).select_from(m.Call).where(
                m.Call.state.in_(["dispatching", "unknown", "in_progress"])))
            last_dispatch = db.scalar(select(func.max(m.Call.dispatched_at)))
            if active >= cfg.max_active_calls or (last_dispatch and now() - last_dispatch < timedelta(seconds=1)):
                # Leave durable intent undelivered; tick republishes it later.
                # Unknown external effects occupy capacity until reconciled.
                event.error = "waiting_for_admission"
                return
            destination = db.get(m.Destination, call.destination_id)
            svc.check_dial_policy(db, svc.customer(db, call.customer_id), destination, now(), exclude_call=call.id)
        except Rejected as error:
            call.state, call.summary, call.ended_at = "cancelled", error.message, now()
            event.delivered_at, event.error = now(), error.code
            return
        call.state, call.dispatched_at = "dispatching", now()
        call.session_token_hash = hashlib.sha256(token.encode()).hexdigest()
        call_id, phone = call.id, destination.phone
        event.delivered_at = now()
    # Network request happens after durable intent; no database/global lock held.
    # Any exception may follow an accepted carrier request. Never auto-retry it.
    try:
        provider_id = asyncio.run(initiate(call_id, phone, token))
    except Exception:
        with session() as db, db.begin():
            call = db.scalar(select(m.Call).where(m.Call.id == call_id).with_for_update())
            if call.state == "dispatching":
                call.state = "unknown"
                db.add(m.Followup(call_id=call.id, kind="internal_review", owner="Sarah", priority=1,
                                 detail="Provider initiation was not acknowledged. Reconcile the existing room/call before any retry.", requested=False))
        return
    with session() as db, db.begin():
        call = db.get(m.Call, call_id)
        call.provider_id = provider_id


@celery.task(name="brightwater.reconcile", acks_late=True)
def reconcile():
    # Unknown external effects need provider evidence, never an invented failure.
    with session() as db, db.begin():
        stale = db.scalars(select(m.Call).where(m.Call.state == "dispatching",
                                               m.Call.dispatched_at < now() - timedelta(seconds=60)).with_for_update(skip_locked=True)).all()
        for call in stale:
            call.state = "unknown"
            db.add(m.Followup(call_id=call.id, kind="internal_review", owner="Sarah", priority=1,
                             detail="Call initiation exceeded the acknowledgement deadline. No automated redial is permitted.", requested=False))


class FencedScheduler(PersistentScheduler):
    leadership_connection = None

    def tick(self, *args, **kwargs):
        connection = self.leadership_connection
        if connection is None or connection.closed or connection.invalidated:
            raise SystemExit("Beat lost its database leadership connection")
        try:
            owns_lock = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid() AND objid=72542191 AND granted)"))
        except Exception:
            raise SystemExit("Beat leadership could not be verified") from None
        if not owns_lock:
            raise SystemExit("Beat no longer owns the scheduling lock")
        return super().tick(*args, **kwargs)


def beat_main():
    # Hold a dedicated connection advisory lock for the scheduler lifetime.
    # Duplicate delivery is still made safe by outbox/dispatch idempotency.
    from brightwater.db import engine
    with engine().connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        if not connection.scalar(text("SELECT pg_try_advisory_lock(72542191)")):
            raise RuntimeError("Another Beat scheduler owns this environment")
        FencedScheduler.leadership_connection = connection
        Service(celery, scheduler_cls=FencedScheduler,
                schedule_filename=f"/tmp/brightwater-beat-{cfg.environment}", max_interval=5).start()


if __name__ == "__main__":
    beat_main()
