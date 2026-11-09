"""Plivo carrier transport to ElevenLabs managed conversation, without an LLM loop.

Carrier authentication/recording/admission remain in plivo_gateway. Local VAD is
used only for original speech evidence; ElevenLabs owns ASR, turns, LLM and TTS.
"""
import asyncio
import base64
import contextlib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from livekit import rtc
from livekit.agents import vad
from livekit.plugins import silero
from websockets.asyncio.client import connect

from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS
from brightwater.managed.readback import compact


@dataclass
class Response:
    event_id: int
    text: str = ""
    alignment: str = ""
    complete: bool = False
    interrupted: bool = False
    bytes_received: int = 0
    bytes_captured: int = 0
    flushed: bool = False
    text_parts: dict = field(default_factory=dict)
    revision: int = 0


class SpeechClock:
    """Retain original packet receive time across buffered/VAD processing."""
    def __init__(self):
        self.frames = deque(maxlen=512)
        self.samples = 0
        self.starts = deque(maxlen=32)
        self.ended = deque(maxlen=32)
        self.active_start = None
        self.opening_boundary = None
        self.preopening_discarded = 0
        self.seen_transcripts = set()
        self.turn_start = None
        self.response_event_floor = -1

    def frame(self, frame):
        at = frame.userdata.get("received_at")
        if type(at) not in {float, int}:
            raise ValueError("Original carrier frame timestamp required")
        self.frames.append((self.samples, frame.samples_per_channel, at - frame.duration))
        self.samples += frame.samples_per_channel

    def speech(self, index, duration, *, sample_rate=8000):
        # Include one inference window conservatively, not the silence padding. Never retimestamp an early yes
        # when the asynchronous transcript arrives after playback has finished.
        if sample_rate not in {8000, 16000}:
            raise ValueError("Unsupported original-speech detector rate")
        # The detector uses the same 16 kHz PCM as hosted ASR. The retained
        # carrier clock remains 8 kHz; convert indices, never receipt times.
        sample = max(0, index * 8000 // sample_rate - int((duration + .032) * 8000))
        frame = next((f for f in reversed(self.frames) if f[0] <= sample), None)
        if frame:
            self.active_start = frame[2] + max(0, min(sample - frame[0], frame[1])) / 8000
            self.starts.append(self.active_start)
            return True
        return False

    def end_speech(self, index, *, sample_rate=16000):
        if sample_rate not in {8000, 16000}:
            raise ValueError("Unsupported original-speech detector rate")
        sample = index * 8000 // sample_rate
        frame = next((f for f in reversed(self.frames) if f[0] <= sample), None)
        if self.active_start is not None and frame:
            # Retain the detector's trailing silence: discard only spans
            # conservatively known to have ended before the first opening.
            end = frame[2] + max(0, min(sample - frame[0], frame[1])) / 8000
            self.ended.append((self.active_start, end))
            self.active_start = None
            self._discard_preopening()

    def begin_opening(self, at):
        if self.opening_boundary is None:
            self.opening_boundary = at
            self._discard_preopening()

    def _discard_preopening(self):
        if self.opening_boundary is None:
            return
        expired = {start for start, end in self.ended if end < self.opening_boundary}
        retained = [start for start in self.starts if start not in expired]
        self.preopening_discarded += len(self.starts) - len(retained)
        self.starts.clear()
        self.starts.extend(retained)

    def transcript(self, event_id):
        if event_id in self.seen_transcripts:
            return None
        self.seen_transcripts.add(event_id)
        if type(event_id) is not int or event_id <= self.response_event_floor:
            return None
        if self.starts:
            start = self.starts[0]
            self.turn_start = start if self.turn_start is None else min(self.turn_start, start)
            self.starts.clear()
        # Provider ASR may split one original speech turn into several final
        # fragments. Reuse its earliest original onset; never receipt time.
        return self.turn_start

    def end_turn(self, event_id):
        self.turn_start = None
        if type(event_id) is int:
            self.response_event_floor = max(self.response_event_floor, event_id)


def alignment_complete(response, audio):
    alignment = audio.get("alignment") or {}
    chars = alignment.get("chars") or []
    starts = alignment.get("char_start_times_ms") or []
    lengths = alignment.get("char_durations_ms") or []
    if not (isinstance(chars, list) and all(isinstance(c, str) for c in chars)):
        raise ValueError("Invalid provider alignment")
    response.alignment += "".join(chars)
    if not response.text or len(chars) != len(starts) or len(chars) != len(lengths):
        return False
    if any(type(x) not in {int, float} or x < 0 for x in starts + lengths):
        raise ValueError("Invalid provider alignment times")
    # Caption durations are estimates and can extend beyond their PCM packet
    # (observed on real provider output). They are not a wire completion clock.
    # Require coverage through the declared final punctuation, then flush and
    # obtain the real carrier checkpoint ACK for all corresponding audio.
    return (compact(response.alignment) == compact(response.text)
        and (response.text.rstrip()[-1] not in ".!?" or response.alignment.rstrip().endswith(response.text.rstrip()[-1])))



class ManagedPlivo:
    def __init__(self, transport, provider, *, customer_name, emit, max_seconds=ATTENDED_CALL_MAX_SECONDS, farewell=None):
        self.transport, self.provider, self.emit = transport, provider, emit
        self.customer_name, self.max_seconds = customer_name, max_seconds
        self.clock = SpeechClock()
        self.responses = {}
        self.output = asyncio.Queue(maxsize=256)
        self.audit = asyncio.Queue(maxsize=256)
        self.queued_bytes = 0
        self.generation = 0
        self.playing = deque()
        self.seen_interruptions = set()
        self.end_requested = asyncio.Event()
        self.boundary_requested = asyncio.Event()
        self.farewell = farewell
        self.segments_done = asyncio.Event()
        self.segments_done.set()
        self.notice_delivered = False
        self.output_error = None
        self.vad_starts = self.vad_mapped_starts = 0
        self.vad_stream = silero.VAD.load(sample_rate=16000, min_speech_duration=.06,
            min_silence_duration=.25, prefix_padding_duration=.3).stream()
        transport.audio_output.on("playback_finished", self.playback_finished)

    def record(self, kind, payload, *, at=None, key=None):
        self.audit.put_nowait((kind, payload, at or time.time(), key))

    async def audits(self):
        while True:
            kind, payload, at, key = await self.audit.get()
            try:
                await self.emit(kind, payload, occurred_at=datetime.fromtimestamp(at, UTC), event_id=key)
            finally:
                self.audit.task_done()

    async def input_audio(self):
        resampler = rtc.AudioResampler(8000, 16000, quality=rtc.AudioResamplerQuality.HIGH)
        async for frame in self.transport.audio_input:
            self.clock.frame(frame)
            for converted in resampler.push(frame):
                self.vad_stream.push_frame(converted)
                await self.provider.send_json({"user_audio_chunk": base64.b64encode(bytes(converted.data)).decode()})

    async def vad_events(self):
        async for event in self.vad_stream:
            if event.type == vad.VADEventType.START_OF_SPEECH:
                self.vad_starts += 1
                if self.clock.speech(event.samples_index, event.speech_duration, sample_rate=16000):
                    self.vad_mapped_starts += 1
            elif event.type == vad.VADEventType.END_OF_SPEECH:
                self.clock.end_speech(event.samples_index, sample_rate=16000)

    def playback_finished(self, event):
        if not self.playing:
            return
        response = self.playing.popleft()
        success = response.complete and not response.interrupted and not event.interrupted
        self.record("agent_utterance", {"source": "plivo_elevenlabs_observer", "text": response.text,
            "playback_completed": success, "interrupted": not success,
            "native_event_id": response.event_id, "revision": response.revision, "alignment_complete": response.complete})
        lower = response.text.lower()
        if success:
            if "ai assistant" in lower and "recorded" in lower and "fictional" in lower:
                self.notice_delivered = True
            question = "Am I speaking with " + self.customer_name + "?"
            if question.lower() in lower:
                self.record("turn_state", {"source": "identity_question", "completed": True,
                    "notice_delivered": self.notice_delivered, "name": self.customer_name, "text": question})
        if not self.playing:
            self.segments_done.set()

    def interrupt(self):
        self.generation += 1
        pending_ids = {r.event_id for r in self.playing}
        for response in list(self.responses.values()) + list(self.playing):
            if not response.flushed or response.event_id in pending_ids:
                response.interrupted = True
        self.transport.audio_output.clear_buffer()
        self.record("interruption", {"source": "plivo_elevenlabs_observer"})

    async def output_audio(self):
        current = None
        resampler = None
        playback = None

        async def flush():
            if current is None or current.flushed or current.interrupted:
                return
            captured = current.bytes_captured
            # Freeze BEFORE awaiting carrier credit for the resampler tail.
            # The receiver may extend this same turn while capture is blocked.
            playback.text = current.text
            playback.revision = current.revision
            playback.alignment = current.alignment
            playback.complete = current.complete and captured == current.bytes_received
            for frame in resampler.flush():
                await self.transport.audio_output.capture_frame(frame)
            if current.interrupted:
                return
            self.transport.audio_output.flush()
            current.flushed = captured == current.bytes_received

        while True:
            try:
                # Caption coverage can precede a trailing PCM packet with no
                # characters. Stream audio immediately; settle only its final
                # checkpoint, normally while carrier playback is still queued.
                timeout = .2 if current else None
                item = await asyncio.wait_for(self.output.get(), timeout)
            except TimeoutError:
                if current.complete:
                    await flush()
                    current = None
                continue
            generation, response, pcm, _ = item
            self.queued_bytes -= len(pcm)
            try:
                if generation != self.generation or response.interrupted:
                    continue
                if current is not response:
                    await flush()
                    current = response
                    resampler = rtc.AudioResampler(16000, 8000, quality=rtc.AudioResamplerQuality.HIGH)
                    playback = Response(response.event_id)
                    self.playing.append(playback)
                    self.segments_done.clear()
                response.flushed = False
                converted = resampler.push(rtc.AudioFrame(pcm, 16000, 1, len(pcm) // 2))
                for frame in converted:
                    data = bytes(frame.data)
                    for offset in range(0, len(data), 8000):
                        if generation != self.generation or response.interrupted:
                            break
                        chunk = data[offset:offset + 8000]
                        await self.transport.audio_output.capture_frame(rtc.AudioFrame(chunk, 8000, 1, len(chunk) // 2))
                if generation == self.generation and not response.interrupted:
                    response.bytes_captured += len(pcm)
            finally:
                self.output.task_done()

    def response_for_audio(self, event_id):
        return self.responses.setdefault(event_id, Response(event_id))

    async def receive(self):
        async for event in self.provider:
            kind = event.get("type")
            if kind == "conversation_initiation_metadata":
                metadata = event["conversation_initiation_metadata_event"]
                if metadata.get("agent_output_audio_format") != "pcm_16000" or metadata.get("user_input_audio_format") != "pcm_16000":
                    raise ValueError("Managed provider codec must use the qualified PCM16 at 16 kHz")
            elif kind == "ping":
                await self.provider.send_json({"type": "pong", "event_id": event["ping_event"]["event_id"]})
            elif kind == "agent_response":
                self.clock.begin_opening(time.time())
                item = event["agent_response_event"]
                identifier = item["event_id"]
                response = self.response_for_audio(identifier)
                response_id = item.get("response_id")
                text = item["agent_response"]
                # Audio for the post-tool answer can begin BEFORE its text
                # event. Keep a cumulative caller-turn caption, rather than
                # assigning those PCM packets to whichever text arrived last.
                if response_id in response.text_parts and response.text_parts[response_id] != text:
                    raise ValueError("Changed managed response without correction")
                if response_id not in response.text_parts:
                    response.revision += 1
                    self.record("turn_state", {"source": "managed_agent_prompt", "completed": False,
                        "native_event_id": identifier, "revision": response.revision})
                response.text_parts[response_id] = text
                response.text = " ".join(response.text_parts.values())
                response.complete = alignment_complete(response, {})
                self.clock.end_turn(identifier)
            elif kind == "audio":
                self.clock.begin_opening(time.time())
                item = event["audio_event"]
                response = self.response_for_audio(item["event_id"])
                pcm = base64.b64decode(item["audio_base_64"], validate=True)
                if not pcm or len(pcm) % 2 or len(pcm) > 320000:
                    raise ValueError("Unexpected managed audio packet")
                response.flushed = False
                response.bytes_received += len(pcm)
                response.complete = alignment_complete(response, item)
                self.queued_bytes += len(pcm)
                if self.queued_bytes > 2_000_000:
                    raise ValueError("Managed output buffer exceeded")
                self.output.put_nowait((self.generation, response, pcm, response.complete))
            elif kind == "interruption":
                identifier = event.get("interruption_event", {}).get("event_id")
                if identifier is None or identifier not in self.seen_interruptions:
                    self.seen_interruptions.add(identifier)
                    self.interrupt()
            elif kind == "agent_response_correction":
                corrected = event.get("agent_response_correction_event", {})
                response = self.responses.get(corrected.get("event_id"))
                if response and not response.interrupted:
                    self.interrupt()
            elif kind == "user_transcript":
                item = event["user_transcription_event"]
                identifier = item["event_id"]
                if identifier in self.clock.seen_transcripts:
                    continue
                started = self.clock.transcript(identifier)
                self.record("user_utterance", {"source": "plivo_elevenlabs_observer", "text": item["user_transcript"],
                    "speech_timing_verified": started is not None, "native_event_id": identifier},
                    at=started, key="managed-caller:" + str(identifier))
            elif kind == "agent_tool_response" and event["agent_tool_response"]["tool_name"] == "end_call":
                self.end_requested.set()
            elif kind in {"error", "client_error"}:
                raise RuntimeError("Managed provider stopped the conversation")

    async def finished(self):
        await self.end_requested.wait()
        # Receiver keeps accepting final audio while carrier checkpoints drain.
        while True:
            await asyncio.sleep(.05)
            audio = [r for r in self.responses.values() if r.bytes_received and not r.interrupted]
            if (self.output.empty() and self.segments_done.is_set()
                and all(r.complete and r.flushed for r in audio)):
                await self.audit.join()
                return

    async def run(self):
        tasks = [asyncio.create_task(method()) for method in (
            self.audits, self.input_audio, self.vad_events, self.output_audio, self.receive, self.finished)]
        watcher = asyncio.create_task(self.transport.wait_closed())
        tasks.append(watcher)
        boundary = asyncio.create_task(self.boundary_requested.wait())
        tasks.append(boundary)
        try:
            done, _ = await asyncio.wait(tasks, timeout=self.max_seconds, return_when=asyncio.FIRST_COMPLETED)
            if self.transport.failure_reason:
                from brightwater.plivo_audio import AudioTransportError
                raise AudioTransportError(self.transport.failure_reason)
            if boundary in done:
                # Stop model/audio production before the goodbye. Keep carrier
                # reception alive and drain caller PCM so a speaking caller
                # cannot overflow its two-second input queue during the closing.
                for task in tasks[1:6]:
                    task.cancel()
                await asyncio.gather(*tasks[1:6], return_exceptions=True)
                self.interrupt()
                self.transport.audio_output.off('playback_finished', self.playback_finished)
                async def drain():
                    async for _ in self.transport.audio_input:
                        pass
                draining = asyncio.create_task(drain())
                played = False
                try:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(self.provider.aclose(), 2)
                    if self.farewell:
                        played = await asyncio.wait_for(self.farewell(), 12)
                except Exception:
                    # A lost provider/line cannot guarantee an audible goodbye.
                    # Still stop resource use rather than continuing indefinitely.
                    played = False
                finally:
                    draining.cancel()
                    await asyncio.gather(draining, return_exceptions=True)
                self.record('turn_state', {'source': 'boundary_closing', 'playback_completed': played})
                await asyncio.wait_for(self.audit.join(), 2)
                return
            for task in done:
                task.result()
            if not done:
                raise TimeoutError("Managed call duration exceeded")
        finally:
            # Transport shutdown queues interrupted playback evidence. Preserve
            # it before cancelling the audit consumer; failure remains fatal.
            if not tasks[0].done():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.audit.join(), 2)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.vad_stream.aclose()
            self.transport.audio_output.off("playback_finished", self.playback_finished)


class ProviderSocket:
    def __init__(self, socket):
        self.socket = socket

    async def send_json(self, value):
        import json
        await self.socket.send(json.dumps(value))

    async def aclose(self):
        await self.socket.close()

    async def __aiter__(self):
        import json
        async for message in self.socket:
            yield json.loads(message)


async def run_managed_phone(app, context, cfg, transport, event):
    response = await app.state.http.post(cfg.api_url + "/runtime/managed/session",
        headers={"Authorization": "Bearer " + context["session_token"],
                 "X-Brightwater-Runtime": cfg.runtime_token.get_secret_value()}, timeout=20)
    response.raise_for_status()
    details = response.json()
    url = urlparse(details["signed_url"])
    if url.scheme != "wss" or url.hostname != "api.elevenlabs.io" or url.path != "/v1/convai/conversation":
        raise ValueError("Unexpected managed provider endpoint")
    async def emit(kind, payload, **kwargs):
        await event(context, kind, payload, **kwargs)
    async with connect(details["signed_url"], max_size=2_000_000, open_timeout=15) as socket:
        provider = ProviderSocket(socket)
        await provider.send_json({"type": "conversation_initiation_client_data",
            "dynamic_variables": {"customer_name": details["customer_name"], "secret__session_token": details["token"]},
            "conversation_config_override": {"conversation": {"text_only": False}}})
        bridge = ManagedPlivo(transport, provider, customer_name=details["customer_name"], emit=emit,
                              max_seconds=max(1, int(context["max_seconds"])))
        from brightwater.managed.closing import farewell
        async def close_politely():
            return await farewell(app.state.http, cfg.elevenlabs_api_key.get_secret_value(),
                                  details['agent_id'], transport.audio_output)
        bridge.farewell = close_politely
        app.state.active_bridges[context['call_id']] = bridge
        try:
            await bridge.run()
        finally:
            if app.state.active_bridges.get(context['call_id']) is bridge:
                del app.state.active_bridges[context['call_id']]
            # Private bounded diagnostic, no PCM, provider key or capability.
            # Optional capture never turns a provider failure into a success.
            with contextlib.suppress(Exception):
                payload = {"call_id": context["call_id"], "transport_failure": transport.failure_reason,
                    "transport_failure_snapshot": transport.failure_snapshot,
                    "transport_close": transport.close_reason, "pending_playback": len(bridge.playing),
                    "vad_sample_rate": 16000, "vad_starts": getattr(bridge, "vad_starts", 0),
                    "vad_mapped_starts": getattr(bridge, "vad_mapped_starts", 0),
                    "preopening_speech_discarded": getattr(getattr(bridge, "clock", None), "preopening_discarded", 0),
                    "responses": [{"event_id": r.event_id, "text": r.text[:8000],
                        "alignment": r.alignment[:8000], "complete": r.complete,
                        "interrupted": r.interrupted, "flushed": r.flushed,
                        "bytes_received": r.bytes_received, "bytes_captured": r.bytes_captured}
                        for r in list(bridge.responses.values())[-32:]]}
                value = app.state.store.cipher.encrypt(json.dumps(payload).encode())
                await asyncio.wait_for(app.state.redis.set("voice:managed-diagnostic:" + context["sid"],
                    value, ex=86400), 1)
