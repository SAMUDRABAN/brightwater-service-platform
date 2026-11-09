"""Correlate SDK caller turns with auditable action confirmation.

ASR completion/receipt time is not when the caller began speaking. Keep the
original SDK speech timestamp, deduplicate pipeline/realtime event paths, and
never reuse a previous turn while a new one is in progress.
"""

import asyncio
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CallerEvidence:
    event_id: str
    epoch: int
    started_at: datetime
    timing_verified: bool
    text: str = field(default="", repr=False)


class CallerTurns:
    def __init__(self, writer):
        self.writer = writer
        self.epoch = 0
        self.speaking = False
        self.latest = None
        self._seen = {}
        self._canonical = {}
        self._latest_start = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()
        self._changed = asyncio.Event()
        self._armed = None
        self._ended_at = datetime.min.replace(tzinfo=UTC)
        self._epoch_floor = self._ended_at
        self._epoch_start = self._ended_at

    def changed(self):
        self._changed.set()
        self._changed = asyncio.Event()

    def begin(self, started_at=None):
        self.epoch += 1
        self._epoch_floor = self._ended_at
        self._epoch_start = datetime.fromtimestamp(started_at, UTC) if isinstance(started_at, (int, float)) and math.isfinite(started_at) else datetime.now(UTC)
        self.speaking = True
        self.latest = None
        self.changed()

    def end(self, stopped_at=None):
        self.speaking = False
        self._ended_at = datetime.fromtimestamp(stopped_at, UTC) if isinstance(stopped_at, (int, float)) and math.isfinite(stopped_at) else datetime.now(UTC)
        self.changed()

    async def record(self, message):
        text = getattr(message, "text_content", None)
        if not text:
            return None
        message_id = str(message.id)
        async with self._lock:
            if message_id in self._seen:
                return self._seen[message_id]
            epoch = self.epoch
            metrics = getattr(message, "metrics", None) or {}
            started = metrics.get("started_speaking_at")
            verified = isinstance(started, (float, int)) and math.isfinite(started)
            at = datetime.fromtimestamp(started, UTC) if verified else datetime.now(UTC)
            if at > datetime.now(UTC):
                verified, at = False, datetime.now(UTC)
            # The SDK can clone a preemptive user message under a different ID.
            # Identical verified source speech is one utterance, even if its
            # clone arrives in a later turn. Retain its original epoch; never
            # refresh stale consent. Different text/source time stays distinct.
            canonical = (at, text) if verified else None
            if canonical is not None and canonical in self._canonical:
                evidence = self._canonical[canonical]
                self._seen[message_id] = evidence
                return evidence
            event_id = await self.writer("user_utterance", {
                "text": text, "sdk_message_id": message_id,
                "turn_epoch": epoch, "speech_timing_verified": verified,
            }, occurred_at=at)
            evidence = CallerEvidence(event_id, epoch, at, verified, text)
            self._seen[message_id] = evidence
            if canonical is not None:
                self._canonical[canonical] = evidence
            stopped = metrics.get("stopped_speaking_at")
            spans_current = isinstance(stopped, (int, float)) and math.isfinite(stopped) and at.timestamp() <= stopped <= datetime.now(UTC).timestamp() and stopped >= self._epoch_start.timestamp()
            if epoch == self.epoch and at >= self._latest_start and (at > self._epoch_floor or spans_current):
                self.latest, self._latest_start = evidence, at
            self.changed()
            return evidence

    async def final(self, timeout=2.0, require_verified=True):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            value = self.latest
            if value and value.epoch == self.epoch and not self.speaking:
                return value if value.timing_verified or not require_verified else None
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            changed = self._changed
            try:
                await asyncio.wait_for(changed.wait(), timeout=remaining)
            except TimeoutError:
                return None

    def arm(self, proposal_id):
        # A caller already speaking before playout completion must speak again.
        self._armed = (proposal_id, self.epoch, datetime.now(UTC))

    def accepts(self, proposal_id, evidence):
        return bool(evidence and evidence.timing_verified and not self.speaking
                    and self._armed and self._armed[0] == proposal_id
                    and self.epoch > self._armed[1] and evidence.started_at >= self._armed[2]
                    and evidence.epoch == self.epoch)
