import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from brightwater.turns import CallerTurns


def message(key, at=None):
    return SimpleNamespace(id=key, text_content="yes please", metrics={
        "started_speaking_at": (at or datetime.now(UTC)).timestamp()})


def test_dual_sdk_paths_write_once_and_preserve_speech_time():
    async def run():
        writes = []

        async def writer(*args, **kwargs):
            writes.append((args, kwargs))
            await asyncio.sleep(0)
            return "event-1"

        turns = CallerTurns(writer)
        at = datetime.now(UTC) - timedelta(seconds=1)
        first, second = await asyncio.gather(turns.record(message("same", at)), turns.record(message("same", at)))
        assert first == second
        assert len(writes) == 1
        assert writes[0][1]["occurred_at"] == at
    asyncio.run(run())


def test_buffered_yes_and_a_new_correction_cannot_confirm(monkeypatch):
    async def run():
        async def writer(*args, **kwargs):
            return "event"

        turns = CallerTurns(writer)
        base = datetime.now(UTC) - timedelta(seconds=2)
        class Clock(datetime):
            current = base + timedelta(milliseconds=150)
            @classmethod
            def now(cls, tz=None):
                return cls.current
        monkeypatch.setattr("brightwater.turns.datetime", Clock)
        turns.begin(started_at=base.timestamp())
        early = message("early", base + timedelta(milliseconds=10))
        turns.end(stopped_at=(base + timedelta(milliseconds=100)).timestamp())
        turns.arm("proposal")
        old = await turns.record(early)
        assert not turns.accepts("proposal", old)
        Clock.current = base + timedelta(milliseconds=350)
        turns.begin(started_at=(base + timedelta(milliseconds=200)).timestamp())
        fresh = message("fresh", base + timedelta(milliseconds=210))
        turns.end(stopped_at=(base + timedelta(milliseconds=300)).timestamp())
        accepted = await turns.record(fresh)
        assert turns.accepts("proposal", accepted)
        Clock.current = base + timedelta(milliseconds=550)
        turns.begin(started_at=(base + timedelta(milliseconds=400)).timestamp())
        assert not turns.accepts("proposal", accepted)
        turns.end(stopped_at=(base + timedelta(milliseconds=500)).timestamp())
        await turns.record(message("late-copy", datetime.fromtimestamp(fresh.metrics["started_speaking_at"], UTC)))
        assert await turns.final(timeout=0.01) is None
    asyncio.run(run())


def test_missing_speech_timing_fails_closed_for_booking():
    async def run():
        async def writer(*args, **kwargs):
            return "event"

        turns = CallerTurns(writer)
        turns.arm("proposal")
        turns.begin()
        turns.end()
        evidence = await turns.record(SimpleNamespace(id="untimed", text_content="yes", metrics={}))
        assert await turns.final() is None
        assert not turns.accepts("proposal", evidence)
        assert await turns.final(require_verified=False) == evidence
    asyncio.run(run())


def test_pending_write_from_previous_turn_cannot_replace_current_turn():
    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def writer(*args, **kwargs):
            started.set()
            await release.wait()
            return "old-event"

        turns = CallerTurns(writer)
        turns.begin()
        task = asyncio.create_task(turns.record(message("old")))
        await started.wait()
        turns.end()
        turns.begin()
        turns.end()
        release.set()
        await task
        assert await turns.final(timeout=0.01) is None
    asyncio.run(run())



def test_semantic_confirmation_can_span_physical_pauses_but_not_an_old_yes():
    async def run():
        async def writer(*args, **kwargs):
            return "event"

        turns = CallerTurns(writer)
        turns.arm("proposal")
        onset = datetime.now(UTC)
        turns.begin(started_at=onset.timestamp())
        turns.end(stopped_at=onset.timestamp())
        turns.begin()
        finished = datetime.now(UTC)
        turns.end(stopped_at=finished.timestamp())
        reply = message("yes-with-pause", onset)
        reply.metrics["stopped_speaking_at"] = finished.timestamp()
        evidence = await turns.record(reply)
        assert turns.accepts("proposal", await turns.final())
        turns.begin()
        turns.end()
        stale = message("late-prior-yes", onset)
        stale.metrics["stopped_speaking_at"] = finished.timestamp()
        await turns.record(stale)
        assert await turns.final(timeout=0.01) is None
        assert not turns.accepts("proposal", evidence)
    asyncio.run(run())


def test_identical_prior_end_timestamp_is_not_fresh_speech():
    async def run():
        async def writer(*args, **kwargs):
            return "event"
        turns=CallerTurns(writer)
        at=datetime.now(UTC)-timedelta(seconds=1)
        turns.begin(started_at=at.timestamp())
        turns.end(stopped_at=at.timestamp())
        turns.begin(started_at=(at+timedelta(milliseconds=1)).timestamp())
        turns.end(stopped_at=(at+timedelta(milliseconds=100)).timestamp())
        await turns.record(message("prior-boundary",at))
        assert await turns.final(timeout=.01) is None
    asyncio.run(run())


def test_cloned_preemptive_message_ids_are_one_source_utterance():
    async def run():
        writes=[]
        async def writer(*args,**kwargs):
            writes.append((args,kwargs))
            return 'single-source-event'
        turns=CallerTurns(writer)
        start=datetime.now(UTC)-timedelta(seconds=1)
        turns.begin(started_at=start.timestamp())
        turns.end(stopped_at=(start+timedelta(milliseconds=100)).timestamp())
        first,clone=await asyncio.gather(turns.record(message('final-sdk-id',start)),turns.record(message('preemptive-clone-id',start)))
        assert len(writes)==1 and first==clone
        assert await turns.final() == first
        # A late clone in a later physical turn cannot refresh old consent.
        turns.begin()
        turns.end()
        late=await turns.record(message('late-clone-id',start))
        assert late==first and len(writes)==1
        assert await turns.final(timeout=.01) is None
    asyncio.run(run())


def test_canonical_dedup_keeps_corrections_and_repeated_new_speech():
    async def run():
        writes=[]
        async def writer(*args,**kwargs):
            writes.append(args)
            return 'event-'+str(len(writes))
        turns=CallerTurns(writer)
        at=datetime.now(UTC)-timedelta(seconds=2)
        first=await turns.record(message('first',at))
        correction=message('corrected',at)
        correction.text_content='No, not that date.'
        second=await turns.record(correction)
        third=await turns.record(message('new-yes',at+timedelta(milliseconds=500)))
        assert len(writes)==3 and len({first.event_id,second.event_id,third.event_id})==3
        assert second.text=='No, not that date.'
        assert 'No, not that date.' not in repr(second)
    asyncio.run(run())
