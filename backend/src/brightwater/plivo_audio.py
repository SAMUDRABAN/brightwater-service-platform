"""Bounded Plivo bidirectional audio bridge for LiveKit Agents 1.8.10.

No calls/account operations occur here. The gateway must authenticate the WS
upgrade, approve the route and bind expected call/account IDs before use.
Default wire format is Plivo's native G.711 mu-law, 8 kHz mono. Linear PCM is
optional and requires explicit byte order. Python 3.12 audioop supplies codecs.
Checkpoint ACKs prove provider playout only, not human hearing/comprehension.
"""

import asyncio
import audioop
import base64
import binascii
import json
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from livekit import rtc
from livekit.agents import io


class AudioTransportError(RuntimeError):
    pass


@dataclass(eq=False)
class _Segment:
    total: int = 0
    acknowledged: int = 0
    completed: bool = False
    started_at: float | None = None


@dataclass
class _Checkpoint:
    segment: _Segment
    position: int
    samples: int
    final: bool
    created: float
    sent: bool = False


@dataclass
class _Command:
    payload: dict[str, Any]
    generation: int | None
    checkpoint: str | None = None


class PlivoAudioInput(io.AudioInput):
    def __init__(self, transport: "PlivoAudioTransport"):
        super().__init__(label="plivo-caller")
        self.transport = transport

    async def __anext__(self) -> rtc.AudioFrame:
        self.transport.input_attached = True
        if self.transport.is_closed and self.transport._input.empty():
            raise StopAsyncIteration
        item = await self.transport._input.get()
        if item is None:
            raise StopAsyncIteration
        # LiveKit exposes an int16 memoryview: len(data) counts samples, not bytes.
        self.transport._input_bytes -= item.data.nbytes
        return item


class PlivoAudioOutput(io.AudioOutput):
    def __init__(self, transport: "PlivoAudioTransport"):
        super().__init__(
            label="plivo-agent",
            capabilities=io.AudioOutputCapabilities(pause=False),
            sample_rate=8000,
        )
        self.transport = transport
        self._segments: deque[_Segment] = deque()
        self._active: _Segment | None = None

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        t = self.transport
        await t.wait_ready()
        if frame.sample_rate != 8000 or frame.num_channels != 1:
            t._fail("output_format_mismatch")
            raise AudioTransportError("Output requires PCM16 mono at 8000 Hz")
        data = bytes(frame.data)
        if (
            not data
            or len(data) % 2
            or len(data) != frame.samples_per_channel * 2
            or len(data) > 32000
        ):
            t._fail("invalid_output_frame")
            raise AudioTransportError("Invalid or oversized output frame")
        generation = t._generation
        await t._wait_clear(generation)
        if generation != t._generation:
            return
        await super().capture_frame(frame)
        if self._active is None:
            self._active = _Segment()
            self._segments.append(self._active)
        segment = self._active
        # 20 ms packets/checkpoints bound provider buffering and credit recovery.
        for offset in range(0, len(data), 320):
            chunk = data[offset : offset + 320]
            if not await t._wait_credit(len(chunk) // 2, generation):
                return
            segment.total += len(chunk) // 2
            t._unacked_samples += len(chunk) // 2
            wire = t._encode(chunk)
            await t._enqueue(
                _Command(
                    {
                        "event": "playAudio",
                        "media": {
                            "contentType": t.codec,
                            "sampleRate": 8000,
                            "payload": base64.b64encode(wire).decode("ascii"),
                        },
                    },
                    generation,
                )
            )
            await t._checkpoint(segment, len(chunk) // 2, False, generation)

    def flush(self) -> None:
        super().flush()
        if self._active is None:
            return
        segment, self._active = self._active, None
        self.transport._checkpoint_nowait(segment, 0, True)

    def clear_buffer(self) -> None:
        # Base clear_buffer is abstract and does not reset capture accounting.
        super().flush()
        self.transport._clear()

    def _interrupt_all(self) -> None:
        super().flush()
        self._active = None
        while self._segments:
            segment = self._segments.popleft()
            self.on_playback_finished(
                playback_position=segment.acknowledged / 8000,
                interrupted=True,
            )

    def _complete_ready(self) -> None:
        while self._segments and self._segments[0].completed:
            segment = self._segments.popleft()
            self.on_playback_finished(playback_position=segment.total / 8000, interrupted=False)


class PlivoAudioTransport:
    """Attach audio_input/output to an AgentSession after a validated start event.

    websocket must offer async send_json(dict) and close(code=int). Its receiver
    calls handle_message() serially. Await wait_closed() and prevent backend
    writes on transport failure; closing the WS is not a carrier hangup API.
    """

    def __init__(
        self,
        websocket: Any,
        *,
        expected_call_id: str,
        expected_account_id: str,
        codec: Literal["audio/x-mulaw", "audio/x-l16"] = "audio/x-mulaw",
        pcm_byte_order: Literal["little", "big"] | None = None,
        input_queue_size: int = 100,
        send_queue_size: int = 128,
        max_buffered_seconds: float = 1.0,
        send_timeout: float = 2.0,
        playback_timeout: float = 5.0,
        start_timeout: float = 5.0,
        verify_start=None,
        startup_preroll: bool = False,
    ):
        if not expected_call_id or not expected_account_id:
            raise ValueError("Explicit call/account binding is required")
        if codec not in {"audio/x-mulaw", "audio/x-l16"}:
            raise ValueError("Unsupported codec")
        if codec == "audio/x-l16" and pcm_byte_order not in {"little", "big"}:
            raise ValueError("L16 requires explicit pcm_byte_order")
        if input_queue_size < 1 or send_queue_size < 4:
            raise ValueError("Queues must be bounded and have positive capacity")
        if (
            not 0.02 <= max_buffered_seconds <= 5
            or min(send_timeout, playback_timeout, start_timeout) <= 0
        ):
            raise ValueError("Invalid transport timeout/buffer bounds")
        self.websocket = websocket
        self.expected_call_id, self.expected_account_id = expected_call_id, expected_account_id
        self.codec, self.pcm_byte_order = codec, pcm_byte_order
        self.verify_start = verify_start
        self.startup_preroll = startup_preroll
        self.input_attached = False
        self.startup_discarded_samples = 0
        self.send_timeout, self.playback_timeout, self.start_timeout = (
            send_timeout,
            playback_timeout,
            start_timeout,
        )
        self._max_samples = int(max_buffered_seconds * 8000)
        self._input: asyncio.Queue[rtc.AudioFrame | None] = asyncio.Queue(input_queue_size)
        self._outgoing: asyncio.Queue[_Command] = asyncio.Queue(send_queue_size)
        self._ready, self._closed, self._clear_ack, self._credit = (
            asyncio.Event() for _ in range(4)
        )
        self._clear_ack.set()
        self._credit.set()
        self.stream_id: str | None = None
        self.failure_reason: str | None = None
        self.failure_snapshot: dict[str, int | float] | None = None
        self.input_failure_stage: str | None = None
        self.close_reason: str | None = None
        self._generation = self._unacked_samples = self._input_bytes = 0
        self._last_sequence = -1
        self._played_count = 0
        self._late_played_count = 0
        self._last_clear_receipt_sequence = -1
        self._clear_sent = False
        self._last_played_at: float | None = None
        self._pending: dict[str, _Checkpoint] = {}
        self._tasks: list[asyncio.Task] = []
        self._close_task: asyncio.Task | None = None
        self._started_at = self._clear_deadline = 0.0
        self.audio_input, self.audio_output = PlivoAudioInput(self), PlivoAudioOutput(self)

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    async def start(self) -> None:
        if self._tasks or self.is_closed:
            raise AudioTransportError("Transport cannot be restarted")
        self._started_at = time.monotonic()
        self._tasks = [asyncio.create_task(self._sender()), asyncio.create_task(self._watchdog())]

    def _check_open(self) -> None:
        if self.is_closed:
            raise AudioTransportError(self.failure_reason or "Transport closed")

    async def wait_ready(self) -> None:
        self._check_open()
        try:
            await asyncio.wait_for(self._ready.wait(), self.start_timeout)
        except TimeoutError:
            self._fail("start_timeout")
            raise AudioTransportError("Timed out waiting for bound start event") from None
        self._check_open()

    async def wait_closed(self) -> str | None:
        await self._closed.wait()
        return self.failure_reason

    async def aclose(self) -> None:
        self._fail("closed", failure=False)
        current = asyncio.current_task()
        await asyncio.gather(*(t for t in self._tasks if t is not current), return_exceptions=True)
        if self._close_task:
            await self._close_task

    async def handle_message(self, message: str | bytes | dict[str, Any]) -> None:
        self._check_open()
        try:
            self.input_failure_stage = "json_shape"
            if isinstance(message, (str, bytes)):
                if len(message) > 65536:
                    raise ValueError
                message = json.loads(message)
            if not isinstance(message, dict) or len(json.dumps(message)) > 65536:
                raise ValueError
            event = message.get("event")
            if event == "connected" and self.stream_id is None:
                return
            self.input_failure_stage = "sequence"
            sequence = message.get("sequenceNumber")
            if type(sequence) is not int or sequence < 0:
                raise ValueError
            if event == "playedStream":
                # Audio replay protection must not discard an asynchronous
                # named playback receipt. Its authority is a sent checkpoint
                # on this authenticated, bound stream, not the caller-media
                # sequence watermark. _played removes it exactly once.
                self.input_failure_stage = "stream_binding"
                if self.stream_id is None or message.get("streamId") != self.stream_id:
                    raise ValueError
                before = self._played_count
                self._played(message.get("name"))
                if sequence <= self._last_sequence:
                    self._late_played_count += self._played_count - before
                return
            if event == "clearedAudio":
                self.input_failure_stage = "stream_binding"
                if self.stream_id is None or message.get("streamId") != self.stream_id:
                    raise ValueError
                # One clear may be outstanding. Deduplicate its receipt against
                # other clear receipts, never against independently arriving
                # caller audio. An old duplicate cannot release a later clear.
                if sequence <= self._last_clear_receipt_sequence:
                    return
                self._last_clear_receipt_sequence = sequence
                if self._clear_sent and not self._clear_ack.is_set():
                    self._clear_ack.set()
                    self._clear_deadline = 0.0
                return
            if sequence <= self._last_sequence:
                return  # WebSocket order is authoritative; do not replay audio.
            self._last_sequence = sequence
            if event == "start":
                self.input_failure_stage = "start_shape"
                start = message["start"]
                fmt = start["mediaFormat"]
                self.input_failure_stage = "start_call_account_binding"
                if self.stream_id is not None or start["callId"] != self.expected_call_id:
                    raise ValueError
                if not isinstance(start["accountId"], str) or not 1 <= len(start["accountId"]) <= 128:
                    raise ValueError
                if self.verify_start is not None:
                    # Some Plivo streams carry an internal numeric account label,
                    # not the public Auth ID. The gateway verifies ownership with
                    # the authenticated carrier API instead of trusting that label.
                    if not await self.verify_start(start):
                        raise ValueError
                    self._check_open()
                elif start["accountId"] != self.expected_account_id:
                    raise ValueError
                self.input_failure_stage = "start_codec"
                if (
                    fmt["encoding"] != self.codec
                    or type(fmt["sampleRate"]) is not int
                    or fmt["sampleRate"] != 8000
                ):
                    raise ValueError
                self.input_failure_stage = "start_stream_id"
                stream_id = start["streamId"]
                if not isinstance(stream_id, str) or not 1 <= len(stream_id) <= 128:
                    raise ValueError
                self.stream_id = stream_id
                self._ready.set()
                return
            self.input_failure_stage = "stream_binding"
            if self.stream_id is None or message.get("streamId") != self.stream_id:
                raise ValueError
            if event == "media":
                media = message["media"]
                self.input_failure_stage = "media_track"
                if media.get("track") != "inbound":
                    raise ValueError
                self.input_failure_stage = "media_payload_encoding"
                payload = media["payload"]
                if not isinstance(payload, str) or not 1 <= len(payload) <= 16384:
                    raise ValueError
                raw = base64.b64decode(payload, validate=True)
                pcm = self._decode(raw)
                self.input_failure_stage = "decoded_audio_bound"
                if (
                    not pcm
                    or len(pcm) % 2
                    or len(pcm) > 3200
                ):
                    raise ValueError
                # Carriers send audio before recording/STT startup completes.
                # Retain only bounded recent pre-roll until the first consumer
                # attaches. After attachment, never silently discard speech.
                if self.startup_preroll and not self.input_attached:
                    while not self._input.empty() and (
                        self._input.full() or self._input_bytes + len(pcm) > 32000
                    ):
                        old = self._input.get_nowait()
                        self._input_bytes -= old.data.nbytes
                        self.startup_discarded_samples += old.samples_per_channel
                if self._input_bytes + len(pcm) > 32000:
                    raise ValueError
                frame = rtc.AudioFrame(
                    pcm, sample_rate=8000, num_channels=1, samples_per_channel=len(pcm) // 2,
                    userdata={"received_at": time.time()}
                )
                self.input_failure_stage = "input_queue_bound"
                self._input.put_nowait(frame)
                self._input_bytes += len(pcm)
            elif event == "stop":
                self._fail("provider_stop", failure=False)
            elif event != "dtmf":
                raise ValueError
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            UnicodeError,
            binascii.Error,
            audioop.error,
            asyncio.QueueFull,
        ):
            self._fail("invalid_or_overflowing_input")
            raise AudioTransportError("Invalid Plivo event or input backpressure") from None

    def _encode(self, pcm: bytes) -> bytes:
        if self.codec == "audio/x-mulaw":
            return audioop.lin2ulaw(pcm, 2)
        return audioop.byteswap(pcm, 2) if self.pcm_byte_order != sys.byteorder else pcm

    def _decode(self, wire: bytes) -> bytes:
        if self.codec == "audio/x-mulaw":
            return audioop.ulaw2lin(wire, 2)
        if len(wire) % 2:
            raise ValueError
        return audioop.byteswap(wire, 2) if self.pcm_byte_order != sys.byteorder else wire

    async def _wait_clear(self, generation: int) -> None:
        try:
            await asyncio.wait_for(self._clear_ack.wait(), self.playback_timeout)
        except TimeoutError:
            self._fail("clear_timeout")
            raise AudioTransportError("Provider did not clear audio") from None
        self._check_open()

    async def _wait_credit(self, samples: int, generation: int) -> bool:
        while self._unacked_samples + samples > self._max_samples:
            self._credit.clear()
            try:
                await asyncio.wait_for(self._credit.wait(), self.playback_timeout)
            except TimeoutError:
                self._fail("playback_backpressure_timeout")
                raise AudioTransportError("Provider playback did not progress") from None
            self._check_open()
            if generation != self._generation:
                return False
        self._check_open()
        return generation == self._generation

    async def _enqueue(self, command: _Command) -> None:
        self._check_open()
        try:
            await asyncio.wait_for(self._outgoing.put(command), self.send_timeout)
        except TimeoutError:
            self._fail("send_queue_timeout")
            raise AudioTransportError("Outbound audio queue is blocked") from None

    def _make_checkpoint(self, segment: _Segment, samples: int, final: bool) -> _Command:
        name = f"bw-{self._generation}-{uuid4().hex}"
        self._pending[name] = _Checkpoint(segment, segment.total, samples, final, time.monotonic())
        return _Command(
            {"event": "checkpoint", "streamId": self.stream_id, "name": name},
            self._generation,
            name,
        )

    async def _checkpoint(
        self, segment: _Segment, samples: int, final: bool, generation: int
    ) -> None:
        if generation != self._generation:
            return
        await self._enqueue(self._make_checkpoint(segment, samples, final))

    def _checkpoint_nowait(self, segment: _Segment, samples: int, final: bool) -> None:
        self._check_open()
        try:
            self._outgoing.put_nowait(self._make_checkpoint(segment, samples, final))
        except asyncio.QueueFull:
            self._fail("flush_queue_overflow")
            raise AudioTransportError("No queue capacity for playback checkpoint") from None

    def _played(self, name: Any) -> None:
        if not isinstance(name, str) or len(name) > 128:
            raise ValueError
        checkpoint = self._pending.get(name)
        if checkpoint is None:
            return  # Duplicate/cleared generation acknowledgement.
        if not checkpoint.sent:
            raise ValueError
        self._played_count += 1
        self._last_played_at = time.monotonic()
        # A checkpoint proves all earlier audio in this segment has played.
        for key, older in list(self._pending.items()):
            if (
                older.segment is checkpoint.segment
                and older.position <= checkpoint.position
                and older.sent
                and (not older.final or key == name)
            ):
                self._unacked_samples -= older.samples
                self._pending.pop(key)
        checkpoint.segment.acknowledged = max(checkpoint.segment.acknowledged, checkpoint.position)
        segment = checkpoint.segment
        if segment.started_at is None and segment.acknowledged > 0:
            # A first sent-frame ACK is evidence that carrier playback began.
            # Report the observation time conservatively, not a fabricated
            # handset onset. SDK speaking state and interruption gating depend
            # on this event; enqueueing audio alone is not playback evidence.
            segment.started_at = time.time()
            self.audio_output.on_playback_started(created_at=segment.started_at)
        if checkpoint.final:
            checkpoint.segment.completed = True
            self.audio_output._complete_ready()
        self._credit.set()

    def _clear(self) -> None:
        self._check_open()
        self._generation += 1
        self._pending.clear()
        self._unacked_samples = 0
        self._credit.set()
        self.audio_output._interrupt_all()
        # Purge stale queued audio while retaining any outstanding clear command.
        controls = []
        while not self._outgoing.empty():
            command = self._outgoing.get_nowait()
            self._outgoing.task_done()
            if command.generation is None:
                controls.append(command)
        for command in controls:
            self._outgoing.put_nowait(command)
        if self._clear_ack.is_set():
            self._clear_ack.clear()
            self._clear_sent = False
            self._clear_deadline = time.monotonic() + self.playback_timeout
            self._outgoing.put_nowait(
                _Command({"event": "clearAudio", "streamId": self.stream_id}, None)
            )

    async def _sender(self) -> None:
        try:
            while not self.is_closed:
                command = await self._outgoing.get()
                try:
                    if command.generation is not None and command.generation != self._generation:
                        continue
                    if command.checkpoint and command.checkpoint in self._pending:
                        self._pending[command.checkpoint].sent = True
                    if command.payload["event"] == "clearAudio":
                        self._clear_sent = True
                    await asyncio.wait_for(
                        self.websocket.send_json(command.payload), self.send_timeout
                    )
                finally:
                    self._outgoing.task_done()
        except asyncio.CancelledError:
            return
        except Exception:
            self._fail("websocket_send_failed")

    async def _watchdog(self) -> None:
        try:
            while not self.is_closed:
                await asyncio.sleep(min(0.05, self.playback_timeout / 4))
                now = time.monotonic()
                if not self._ready.is_set() and now - self._started_at > self.start_timeout:
                    self._fail("start_timeout")
                elif self._clear_deadline and now > self._clear_deadline:
                    self._fail("clear_timeout")
                elif any(
                    now - checkpoint.created > self.playback_timeout
                    for checkpoint in self._pending.values()
                ):
                    self._fail("playback_checkpoint_timeout")
        except asyncio.CancelledError:
            return

    def _fail(self, reason: str, *, failure: bool = True) -> None:
        if self.is_closed:
            return
        if failure:
            # Preserve numeric evidence BEFORE cleanup discards pending ACKs.
            # Do not retain audio, checkpoint names, call IDs or credentials.
            now = time.monotonic()
            pending = list(self._pending.values())
            self.failure_snapshot = {
                "pending_checkpoints": len(pending),
                "sent_checkpoints": sum(c.sent for c in pending),
                "final_checkpoints": sum(c.final for c in pending),
                "oldest_checkpoint_age_seconds": max(
                    (max(0.0, now - c.created) for c in pending), default=0.0
                ),
                "unacknowledged_samples": self._unacked_samples,
                "acknowledgements_received": self._played_count,
                "late_sequence_acknowledgements_received": self._late_played_count,
                "seconds_since_acknowledgement": (
                    max(0.0, now - self._last_played_at)
                    if self._last_played_at is not None else -1.0
                ),
                "queued_commands": self._outgoing.qsize(),
                "input_queued_bytes": self._input_bytes,
                "generation": self._generation,
            }
        self.close_reason = reason
        self.failure_reason = reason if failure else None
        self._closed.set()
        self._ready.set()
        self._clear_ack.set()
        self._credit.set()
        self._pending.clear()
        self._unacked_samples = 0
        self.audio_output._interrupt_all()
        while not self._outgoing.empty():
            self._outgoing.get_nowait()
            self._outgoing.task_done()
        while not self._input.empty():
            self._input.get_nowait()
        self._input_bytes = 0
        self._input.put_nowait(None)
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
        self._close_task = asyncio.create_task(self._close_socket())

    async def _close_socket(self) -> None:
        try:
            await asyncio.wait_for(
                self.websocket.close(code=1011 if self.failure_reason else 1000), self.send_timeout
            )
        except Exception:
            pass
