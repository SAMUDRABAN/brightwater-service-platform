import asyncio
import base64
import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from test_plivo_gateway import config

from brightwater.plivo_gateway import create_app
from brightwater.twilio_voice import TwilioMedia

ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
STREAM = "MZ" + "3" * 32
RECORDING = "RE" + "4" * 32
CALLER = "+442079460123"
RECIPIENT = "+442079460124"
TOKEN = "test-only"


def test_twilio_answer_binds_signed_call_and_recording_once():
    cfg = config(gateway_country="GB", gateway_carrier="twilio", voice_backend="elevenlabs",
                 twilio_account_sid=ACCOUNT, twilio_auth_token=TOKEN, twilio_from_number=CALLER)
    app = create_app(cfg)
    state = {"purpose": "campaign", "phone": RECIPIENT, "created": time.time(), "status": "initiating"}

    class Store:
        async def get(self, sid):
            return dict(state) if sid == "fixture" else None

        async def put(self, sid, context):
            state.update(context)

    class Redis:
        def __init__(self):
            self.values = {}
            self.jobs = []

        @asynccontextmanager
        async def lock(self, *args, **kwargs):
            yield

        async def set(self, key, value, *, nx, ex):
            if key in self.values:
                return False
            self.values[key] = value.encode()
            return True

        async def get(self, key):
            return self.values.get(key)

        async def rpush(self, key, value):
            self.jobs.append((key, value))

    app.state.store, app.state.redis = Store(), Redis()
    client = TestClient(app)

    def post(path, fields):
        text = cfg.gateway_origin + path + "".join(k + v for k, v in sorted(fields.items()))
        signature = base64.b64encode(hmac.new(TOKEN.encode(), text.encode(), hashlib.sha1).digest()).decode()
        return client.post(path, data=fields, headers={"X-Twilio-Signature": signature})

    answer = "/twilio/answer/fixture"
    fields = {"AccountSid": ACCOUNT, "CallSid": CALL, "From": CALLER, "To": RECIPIENT}
    assert client.post(answer, data=fields).status_code == 403
    assert post(answer, fields | {"To": "+442079460125"}).status_code == 403
    response = post(answer, fields)
    assert response.status_code == 200
    assert 'wss://voice.example.test/twilio/media/fixture' in response.text
    assert state["call_uuid"] == CALL
    recording = "/twilio/recording/fixture"
    callback = {"AccountSid": ACCOUNT, "CallSid": CALL, "RecordingSid": RECORDING}
    assert post(recording, callback | {"CallSid": "CA" + "5" * 32, "RecordingStatus": "completed"}).status_code == 403
    assert post(recording, callback | {"RecordingStatus": "in-progress"}).status_code == 200
    for _ in range(2):
        assert post(recording, callback | {"RecordingStatus": "completed"}).status_code == 200
    assert app.state.redis.jobs == [("voice:recordings", "fixture")]


def test_twilio_media_maps_playback_and_clear_separately():
    class Socket:
        def __init__(self):
            self.received = []
            self.sent = []

        async def receive_text(self):
            return json.dumps(self.received.pop(0))

        async def send_json(self, value):
            self.sent.append(value)

    async def scenario():
        socket = Socket()
        socket.received = [
            {"event": "connected", "protocol": "Call"},
            {"event": "start", "sequenceNumber": "1", "streamSid": STREAM,
             "start": {"accountSid": ACCOUNT, "callSid": CALL, "streamSid": STREAM,
                       "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}},
            {"event": "mark", "sequenceNumber": "2", "streamSid": STREAM, "mark": {"name": "old"}},
            {"event": "mark", "sequenceNumber": "3", "streamSid": STREAM, "mark": {"name": "twilio-clear-1"}},
        ]
        bridge = TwilioMedia(socket)
        assert json.loads(await bridge.receive_text())["start"]["callId"] == CALL
        await bridge.send_json({"event": "playAudio", "media": {"payload": "AA=="}})
        await bridge.send_json({"event": "checkpoint", "name": "old"})
        await bridge.send_json({"event": "clearAudio"})
        assert [item["event"] for item in socket.sent] == ["media", "mark", "clear", "mark"]
        old = json.loads(await bridge.receive_text())
        assert old["event"] == "playedStream" and old["name"] == "old"
        assert json.loads(await bridge.receive_text())["event"] == "clearedAudio"

    asyncio.run(scenario())
