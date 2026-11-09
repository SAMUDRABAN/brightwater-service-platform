"""Protocol/SDK integration tests; fake WebSocket, no network/provider calls."""

import asyncio
import base64
import struct

import pytest
from livekit import rtc

from brightwater.plivo_audio import AudioTransportError, PlivoAudioTransport


@pytest.fixture(autouse=True)
def database():
    """Override the application's unrelated autouse database fixture."""
    yield


class FakeSocket:
    def __init__(self, block=False):
        self.sent = []
        self.closed = []
        self.block = block

    async def send_json(self, message):
        if self.block:
            await asyncio.Event().wait()
        self.sent.append(message)

    async def close(self, code):
        self.closed.append(code)


def frame(samples=160, value=0):
    return rtc.AudioFrame(
        struct.pack(f"={samples}h", *([value] * samples)),
        sample_rate=8000,
        num_channels=1,
        samples_per_channel=samples,
    )


async def ready(**kwargs):
    ws = FakeSocket()
    transport = PlivoAudioTransport(
        ws, expected_call_id="call", expected_account_id="account", **kwargs
    )
    await transport.start()
    await transport.handle_message(
        {
            "event": "start",
            "sequenceNumber": 1,
            "start": {
                "callId": "call",
                "accountId": "account",
                "streamId": "stream",
                "mediaFormat": {"encoding": transport.codec, "sampleRate": 8000},
            },
        }
    )
    return transport, ws


async def drained(transport):
    await asyncio.wait_for(transport._outgoing.join(), 1)


def ack(name, sequence=2):
    return {"event": "playedStream", "sequenceNumber": sequence, "streamId": "stream", "name": name}


@pytest.mark.parametrize("ack_sequence", range(2, 10))
def test_named_playback_ack_is_not_discarded_when_caller_media_has_advanced(ack_sequence):
    async def scenario():
        transport, ws = await ready(playback_timeout=.15)
        try:
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.flush()
            await drained(transport)
            # Force the independently produced inbound media to arrive first.
            media = {"event": "media", "sequenceNumber": 100, "streamId": "stream",
                "media": {"track": "inbound", "payload": base64.b64encode(b"\xff" * 160).decode()}}
            await transport.handle_message(media)
            checkpoint = ws.sent[-1]["name"]
            await transport.handle_message(ack(checkpoint, ack_sequence))
            result = await asyncio.wait_for(transport.audio_output.wait_for_playout(), .5)
            assert not result.interrupted
            assert not transport.is_closed
            assert transport._unacked_samples == 0
            # ACK receipt must not rewind media replay protection.
            await transport.handle_message(media)
            assert transport._input.qsize() == 1
            await transport.handle_message(ack(checkpoint, ack_sequence))
            assert transport._played_count == 1
        finally:
            await transport.aclose()
    asyncio.run(scenario())


def test_late_named_ack_still_requires_bound_stream():
    async def scenario():
        transport, ws = await ready()
        try:
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.flush()
            await drained(transport)
            transport._last_sequence = 100
            message = ack(ws.sent[-1]["name"], 2)
            message["streamId"] = "other-stream"
            with pytest.raises(AudioTransportError):
                await transport.handle_message(message)
            assert transport._played_count == 0
        finally:
            await transport.aclose()
    asyncio.run(scenario())


def test_clear_receipt_can_lag_media_but_old_clear_receipt_cannot_release_new_clear():
    async def scenario():
        transport, ws = await ready(playback_timeout=.2)
        try:
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.clear_buffer()
            await drained(transport)
            transport._last_sequence = 100
            first = {"event": "clearedAudio", "sequenceNumber": 3, "streamId": "stream"}
            await transport.handle_message(first)
            assert transport._clear_ack.is_set()
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.clear_buffer()
            await drained(transport)
            assert not transport._clear_ack.is_set()
            await transport.handle_message(first)
            assert not transport._clear_ack.is_set(), "Old clear receipt cannot acknowledge the next clear"
            await transport.handle_message({**first, "sequenceNumber": 4})
            assert transport._clear_ack.is_set()
            assert transport._last_sequence == 100
            assert transport.failure_reason is None
        finally:
            await transport.aclose()
    asyncio.run(scenario())


def test_mulaw_input_decodes_and_replayed_media_is_not_delivered_twice():
    async def scenario():
        transport, _ = await ready()
        message = {
            "event": "media",
            "sequenceNumber": 2,
            "streamId": "stream",
            "media": {
                "track": "inbound",
                "payload": base64.b64encode(b"\xff" * 160).decode(),
            },
        }
        await transport.handle_message(message)
        await transport.handle_message(message)
        audio = await transport.audio_input.__anext__()
        assert audio.sample_rate == 8000
        assert bytes(audio.data) == b"\x00" * 320
        assert transport._input.empty()
        assert transport._input_bytes == 0
        await transport.aclose()
        with pytest.raises(StopAsyncIteration):
            await transport.audio_input.__anext__()

    asyncio.run(scenario())


def test_continuously_consumed_audio_does_not_leak_input_buffer_accounting():
    async def scenario():
        transport, _ = await ready()
        for sequence in range(2, 302):
            await transport.handle_message(
                {
                    "event": "media",
                    "sequenceNumber": sequence,
                    "streamId": "stream",
                    "media": {
                        "track": "inbound",
                        "payload": base64.b64encode(b"\xff" * 160).decode(),
                    },
                }
            )
            await transport.audio_input.__anext__()
        assert transport._input_bytes == 0 and not transport.is_closed
        await transport.aclose()

    asyncio.run(scenario())


def test_wrong_stream_and_malformed_media_close_transport():
    async def scenario():
        for event in [
            {"event": "media", "sequenceNumber": 2, "streamId": "wrong", "media": {}},
            {"event": "media", "sequenceNumber": 2, "streamId": "stream", "media": None},
        ]:
            transport, _ = await ready()
            with pytest.raises(AudioTransportError):
                await transport.handle_message(event)
            assert transport.is_closed
            await transport.aclose()

    asyncio.run(scenario())


def test_flush_finishes_only_for_matching_provider_checkpoint_once():
    async def scenario():
        transport, ws = await ready()
        events = []
        transport.audio_output.on("playback_finished", events.append)
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.flush()
        await drained(transport)
        assert [m["event"] for m in ws.sent] == ["playAudio", "checkpoint", "checkpoint"]
        assert base64.b64decode(ws.sent[0]["media"]["payload"]) == b"\xff" * 160
        assert not events
        await transport.handle_message(ack("unknown"))
        assert not events
        final = ws.sent[-1]["name"]
        await transport.handle_message(ack(final, 3))
        await transport.handle_message(ack(final, 4))
        result = await transport.audio_output.wait_for_playout()
        assert len(events) == 1 and result.interrupted is False
        assert result.playback_position == 0.02
        assert transport._unacked_samples == 0
        await transport.aclose()

    asyncio.run(scenario())


def test_clear_invalidates_old_acks_resets_sdk_and_holds_new_audio_until_clear_ack():
    async def scenario():
        transport, ws = await ready()
        events = []
        transport.audio_output.on("playback_finished", events.append)
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.flush()
        await drained(transport)
        old = ws.sent[-1]["name"]
        transport.audio_output.clear_buffer()
        await drained(transport)
        assert ws.sent[-1]["event"] == "clearAudio"
        assert len(events) == 1 and events[0].interrupted
        assert transport.audio_output._pending_playback_count == 0
        next_audio = asyncio.create_task(transport.audio_output.capture_frame(frame()))
        await asyncio.sleep(0)
        assert not next_audio.done()
        await transport.handle_message(ack(old))
        assert len(events) == 1
        await transport.handle_message(
            {"event": "clearedAudio", "sequenceNumber": 3, "streamId": "stream"}
        )
        await next_audio
        transport.audio_output.flush()
        await drained(transport)
        new = ws.sent[-1]["name"]
        assert new != old
        await transport.handle_message(ack(new, 4))
        assert len(events) == 2 and events[-1].interrupted is False
        assert transport.audio_output.captured_playout_segments == 2
        assert not transport.audio_output.can_pause
        await transport.aclose()

    asyncio.run(scenario())


def test_clear_of_unflushed_segment_counts_once_and_new_segment_can_finish():
    async def scenario():
        transport, ws = await ready()
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.clear_buffer()
        transport.audio_output.clear_buffer()
        await drained(transport)
        assert sum(m["event"] == "clearAudio" for m in ws.sent) == 1
        assert transport.audio_output._pending_playback_count == 0
        await transport.handle_message(
            {"event": "clearedAudio", "sequenceNumber": 2, "streamId": "stream"}
        )
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.flush()
        await drained(transport)
        await transport.handle_message(ack(ws.sent[-1]["name"], 3))
        assert (await transport.audio_output.wait_for_playout()).interrupted is False
        await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", ["!!bad!!", "A", "", "a" * 17000])
def test_invalid_base64_or_payload_bounds_fail_closed(payload):
    async def scenario():
        transport, ws = await ready()
        with pytest.raises(AudioTransportError):
            await transport.handle_message(
                {
                    "event": "media",
                    "sequenceNumber": 2,
                    "streamId": "stream",
                    "media": {"track": "inbound", "payload": payload},
                }
            )
        assert transport.is_closed and transport.failure_reason
        await transport.aclose()
        assert ws.closed == [1011]

    asyncio.run(scenario())


def test_wrong_bound_call_or_codec_rejected_before_readiness():
    async def scenario():
        ws = FakeSocket()
        transport = PlivoAudioTransport(ws, expected_call_id="call", expected_account_id="account")
        await transport.start()
        with pytest.raises(AudioTransportError):
            await transport.handle_message(
                {
                    "event": "start",
                    "sequenceNumber": 1,
                    "start": {
                        "callId": "another-call",
                        "accountId": "account",
                        "streamId": "stream",
                        "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000},
                    },
                }
            )
        assert transport.is_closed
        await transport.aclose()

    asyncio.run(scenario())


def test_input_backpressure_fails_instead_of_dropping_speech():
    async def scenario():
        transport, _ = await ready(input_queue_size=1)
        for sequence in [2, 3]:
            event = {
                "event": "media",
                "sequenceNumber": sequence,
                "streamId": "stream",
                "media": {"track": "inbound", "payload": base64.b64encode(b"\xff" * 160).decode()},
            }
            if sequence == 2:
                await transport.handle_message(event)
            else:
                with pytest.raises(AudioTransportError):
                    await transport.handle_message(event)
        assert transport.is_closed
        await transport.aclose()

    asyncio.run(scenario())


def test_startup_preroll_stays_bounded_until_first_consumer_then_overflow_fails():
    async def scenario():
        transport, _ = await ready(input_queue_size=3, startup_preroll=True)
        for sequence in range(2, 152):
            await transport.handle_message({
                "event": "media", "sequenceNumber": sequence, "streamId": "stream",
                "media": {"track": "inbound", "payload": base64.b64encode(b"\xff" * 160).decode()},
            })
        assert not transport.is_closed
        assert transport._input.qsize() == 3 and transport._input_bytes == 960
        assert transport.startup_discarded_samples == 147 * 160
        await transport.audio_input.__anext__()
        assert transport.input_attached
        await transport.handle_message({"event": "media", "sequenceNumber": 152, "streamId": "stream",
            "media": {"track": "inbound", "payload": base64.b64encode(b"\xff" * 160).decode()}})
        with pytest.raises(AudioTransportError):
            await transport.handle_message({"event": "media", "sequenceNumber": 153, "streamId": "stream",
                "media": {"track": "inbound", "payload": base64.b64encode(b"\xff" * 160).decode()}})
        await transport.aclose()
    asyncio.run(scenario())


def test_unacknowledged_playback_times_out_and_releases_waiters_as_interrupted():
    async def scenario():
        transport, _ = await ready(playback_timeout=0.05)
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.flush()
        await drained(transport)
        await asyncio.wait_for(transport.wait_closed(), 0.5)
        assert transport.failure_reason == "playback_checkpoint_timeout"
        snapshot = transport.failure_snapshot
        assert snapshot["pending_checkpoints"] == 2
        assert snapshot["sent_checkpoints"] == 2
        assert snapshot["final_checkpoints"] == 1
        assert snapshot["unacknowledged_samples"] == 160
        assert snapshot["oldest_checkpoint_age_seconds"] >= .05
        # Cleanup still releases playback; diagnostics retain only bounded
        # counts/timings, never audio, checkpoint capabilities or call IDs.
        assert not transport._pending
        assert all(type(value) in {int, float} for value in snapshot.values())
        assert (await transport.audio_output.wait_for_playout()).interrupted
        await transport.aclose()
        assert transport.failure_snapshot == snapshot

    asyncio.run(scenario())


def test_slow_socket_send_times_out_without_false_completion():
    async def scenario():
        transport, ws = await ready(send_timeout=0.03)
        ws.block = True
        await transport.audio_output.capture_frame(frame())
        transport.audio_output.flush()
        await asyncio.wait_for(transport.wait_closed(), 0.5)
        assert transport.failure_reason == "websocket_send_failed"
        assert (await transport.audio_output.wait_for_playout()).interrupted
        await transport.aclose()

    asyncio.run(scenario())


def test_bounded_provider_audio_credit_recovers_from_progress_checkpoint():
    async def scenario():
        transport, ws = await ready(max_buffered_seconds=0.02)
        capture = asyncio.create_task(transport.audio_output.capture_frame(frame(samples=320)))
        await asyncio.sleep(0.01)
        await drained(transport)
        assert not capture.done()
        assert transport._unacked_samples == 160
        await transport.handle_message(ack(ws.sent[-1]["name"]))
        await capture
        transport.audio_output.flush()
        await drained(transport)
        await transport.handle_message(ack(ws.sent[-1]["name"], 3))
        assert (await transport.audio_output.wait_for_playout()).playback_position == 0.04
        await transport.aclose()

    asyncio.run(scenario())


def test_explicit_l16_byte_order_and_normal_disconnect():
    with pytest.raises(ValueError, match="explicit pcm_byte_order"):
        PlivoAudioTransport(
            FakeSocket(),
            expected_call_id="call",
            expected_account_id="account",
            codec="audio/x-l16",
        )

    async def scenario():
        transport, _ = await ready(codec="audio/x-l16", pcm_byte_order="big")
        await transport.handle_message(
            {
                "event": "media",
                "sequenceNumber": 2,
                "streamId": "stream",
                "media": {
                    "track": "inbound",
                    "payload": base64.b64encode(struct.pack(">h", 1000)).decode(),
                },
            }
        )
        sample = await transport.audio_input.__anext__()
        assert bytes(sample.data) == struct.pack("=h", 1000)
        await transport.handle_message({"event": "stop", "sequenceNumber": 3, "streamId": "stream"})
        assert transport.is_closed and transport.failure_reason is None
        await transport.aclose()

    asyncio.run(scenario())


def test_start_sequence_zero_is_valid_and_duplicate_zero_is_not_replayed():
    async def run():
        socket = FakeSocket()
        transport = PlivoAudioTransport(socket, expected_call_id="call", expected_account_id="account")
        await transport.start()
        start = {"event": "start", "sequenceNumber": 0, "start": {"callId": "call", "accountId": "account", "streamId": "stream", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000}}}
        await transport.handle_message(start)
        await transport.wait_ready()
        await transport.handle_message(start)
        assert transport.stream_id == "stream" and not transport.is_closed
        await transport.aclose()
    asyncio.run(run())


def test_playback_start_requires_carrier_ack_and_is_once_per_segment():
    async def run():
        transport, ws = await ready()
        events=[]
        transport.audio_output.on('playback_started',events.append)
        try:
            await transport.audio_output.capture_frame(frame(samples=320))
            transport.audio_output.flush()
            await drained(transport)
            checkpoints=[v['name'] for v in ws.sent if v['event']=='checkpoint']
            assert not events, 'Queueing audio must not claim playback'
            await transport.handle_message(ack(checkpoints[0],2))
            assert len(events)==1 and events[0].created_at>0
            await transport.handle_message(ack(checkpoints[0],3))
            await transport.handle_message(ack(checkpoints[1],4))
            await transport.handle_message(ack(checkpoints[-1],5))
            assert len(events)==1
            await transport.audio_output.capture_frame(frame())
            transport.audio_output.flush()
            await drained(transport)
            next_checkpoint=[v['name'] for v in ws.sent if v['event']=='checkpoint'][-1]
            await transport.handle_message(ack(next_checkpoint,6))
            assert len(events)==2
        finally:
            await transport.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("interrupted", [False, True])
def test_actual_sdk_reports_speaking_before_completion_from_plivo_ack(interrupted):
    from livekit.agents import Agent, AgentSession, TurnHandlingOptions
    from livekit.agents.utils import http_context

    async def run():
        transport, ws=await ready()
        states=[]
        async with http_context.open():
            session=AgentSession(turn_handling=TurnHandlingOptions(turn_detection='manual'))
            session.output.audio=transport.audio_output
            session.on('agent_state_changed',lambda event:states.append(event.new_state))
            try:
                await session.start(Agent(instructions='Offline transport test'))
                async def audio():
                    yield frame(samples=320)
                speech=session.say('Offline test audio',audio=audio())
                for _ in range(100):
                    await asyncio.sleep(.01)
                    if sum(v['event']=='checkpoint' for v in ws.sent)>=3:
                        break
                await drained(transport)
                checkpoints=[v['name'] for v in ws.sent if v['event']=='checkpoint']
                assert len(checkpoints)>=3
                assert 'speaking' not in states
                await transport.handle_message(ack(checkpoints[0],2))
                await asyncio.sleep(.02)
                assert 'speaking' in states, 'SDK never learned that its audio was playing'
                assert transport.audio_output._pending_playback_count==1
                if interrupted:
                    session.interrupt()
                    for _ in range(50):
                        await asyncio.sleep(.01)
                        if any(v['event']=='clearAudio' for v in ws.sent):
                            break
                    assert any(v['event']=='clearAudio' for v in ws.sent)
                    await transport.handle_message({'event':'clearedAudio','sequenceNumber':3,'streamId':'stream'})
                    await asyncio.wait_for(speech.wait_for_playout(),2)
                    assert speech.interrupted
                else:
                    await transport.handle_message(ack(checkpoints[-1],3))
                    await asyncio.wait_for(speech.wait_for_playout(),2)
            finally:
                await session.aclose()
                await transport.aclose()
    asyncio.run(run())
