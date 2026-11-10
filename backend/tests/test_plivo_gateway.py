import io
import wave

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from brightwater.plivo_gateway import GatewaySettings, create_app, to_ogg


def config(**changes):
    values = dict(gateway_origin="https://voice.example.test", gateway_token="a" * 40,
        gateway_state_key=Fernet.generate_key().decode(), redis_url="redis://127.0.0.1:1/0",
        plivo_auth_id="test-account", plivo_auth_token="not-a-real-key", plivo_from_number="+912212345678",
        engineering_recipient="+919876543210", api_url="https://office-api.example.test", runtime_token="b" * 40,
        openai_api_key="test-not-real", elevenlabs_api_key="test-not-real")
    return GatewaySettings(**(values | changes))


class MissingState:
    async def get(self, key):
        return None


def test_unauthenticated_provider_requests_cannot_start_a_session():
    app = create_app(config())
    app.state.store = MissingState()
    # No lifespan, models or real Redis/network are needed for denial tests.
    client = TestClient(app)
    assert client.post("/plivo/answer/unknown", data={"CallUUID": "not-real"}).status_code == 403
    assert client.post("/plivo/status/unknown", data={"CallUUID": "not-real"}).status_code == 403
    assert client.post("/plivo/recording-start/unknown", data={"CallUUID": "not-real"}).status_code == 403
    assert client.post("/v1/outbound", json={"call_id": "11111111-1111-1111-1111-111111111111",
        "phone": "+919876543210", "session_token": "not-real", "purpose": "engineering"}).status_code == 401
    with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect("/plivo/media/unknown?token=forged"):
        pass
    assert error.value.code == 1008


def test_answer_starts_background_recording_before_stream_without_redirecting():
    from xml.etree.ElementTree import fromstring

    from brightwater.plivo_gateway import answer_xml
    cfg = config()
    root = fromstring(answer_xml(cfg, 'owned-session', 'test-capability'))
    assert [e.tag for e in root] == ['Record', 'Stream']
    record = root[0]
    assert record.attrib['recordSession'] == 'true'
    assert record.attrib['redirect'] == 'false'
    assert record.attrib['fileFormat'] == 'wav'
    assert record.attrib['recordChannelType'] == 'stereo'
    assert record.attrib['action'] == cfg.gateway_origin + '/plivo/recording-start/owned-session'
    assert record.attrib['callbackUrl'] == cfg.gateway_origin + '/plivo/recording/owned-session'


def test_signed_recording_start_binds_one_id_and_final_callback_queues_once():
    import base64
    import hashlib
    import hmac

    from brightwater.plivo_security import v3_canonical_string

    context = {'call_uuid': '11111111-1111-1111-1111-111111111111',
        'recording_requested': True, 'answer_verified': True}
    identifier = '22222222-2222-2222-2222-222222222222'

    class Store:
        async def get(self, sid):
            return context if sid == 'owned-session' else None

    class Broker:
        def __init__(self):
            self.values, self.jobs = {}, []
        async def set(self, key, value, **kw):
            if kw.get('nx') and key in self.values:
                return False
            self.values[key] = value.encode()
            return True
        async def get(self, key):
            return self.values.get(key)
        async def rpush(self, key, value):
            self.jobs.append(value)

    cfg = config()
    app = create_app(cfg)
    broker = Broker()
    app.state.store, app.state.redis = Store(), broker
    client = TestClient(app)
    def signed_post(path, *, data):
        nonce = 'synthetic-nonce'
        message = v3_canonical_string('POST', cfg.gateway_origin + path, data) + '.' + nonce
        signature = base64.b64encode(hmac.new(cfg.plivo_auth_token.get_secret_value().encode(), message.encode(), hashlib.sha256).digest()).decode()
        return client.post(path, data=data, headers={'X-Plivo-Signature-V3-Nonce': nonce, 'X-Plivo-Signature-V3': signature})
    start = '/plivo/recording-start/owned-session'
    final = '/plivo/recording/owned-session'
    packet = {'CallUUID': context['call_uuid'], 'RecordingID': identifier, 'RecordingDuration': '-1'}
    assert client.post(start, data=packet).status_code == 403
    assert signed_post(final, data=packet).status_code == 403
    assert signed_post(start, data=packet | {'CallUUID': 'wrong'}).status_code == 403
    context['answer_verified'] = False
    assert signed_post(start, data=packet).status_code == 403
    context['answer_verified'] = True
    assert signed_post(start, data=packet | {'RecordingDuration': '1'}).status_code == 400
    assert signed_post(start, data=packet | {'RecordingID': 'invalid'}).status_code == 400
    assert signed_post(start, data=packet).status_code == 200
    assert signed_post(start, data=packet).status_code == 200
    assert signed_post(start, data=packet | {'RecordingID': '33333333-3333-3333-3333-333333333333'}).status_code == 409
    assert signed_post(final, data=packet | {'RecordingID': 'wrong'}).status_code == 403
    assert signed_post(final, data=packet | {'RecordingDuration': '12'}).status_code == 200
    assert signed_post(final, data=packet | {'RecordingDuration': '12'}).status_code == 200
    assert broker.jobs == ['owned-session']


def test_agent_waits_for_confirmed_recording_and_times_out_without_it():
    import asyncio

    from brightwater.plivo_gateway import confirmed_recording

    class Broker:
        identifier = None
        async def get(self, key):
            assert key == 'voice:recording-id:owned-session'
            return self.identifier
    async def scenario():
        broker = Broker()
        with pytest.raises(TimeoutError):
            await confirmed_recording(broker, 'owned-session', timeout=.01)
        broker.identifier = b'22222222-2222-2222-2222-222222222222'
        assert await confirmed_recording(broker, 'owned-session') == broker.identifier.decode()
    asyncio.run(scenario())


def test_authenticated_gateway_still_refuses_disabled_or_different_recipient():
    client = TestClient(create_app(config()))
    response = client.post("/v1/outbound", headers={"Authorization": "Bearer " + "a" * 40},
        json={"call_id": "11111111-1111-1111-1111-111111111111", "phone": "+919876543210",
        "session_token": "not-real", "purpose": "engineering"})
    assert response.status_code == 403
    enabled = TestClient(create_app(config(gateway_enabled=True)))
    response = enabled.post("/v1/outbound", headers={"Authorization": "Bearer " + "a" * 40},
        json={"call_id": "11111111-1111-1111-1111-111111111111", "phone": "+919876543211",
        "session_token": "not-real", "purpose": "engineering"})
    assert response.status_code == 403


def test_actual_recording_conversion_preserves_duplex_playable_audio():
    av = pytest.importorskip("av")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0" * 8000 * 2 * 2)
    encoded = to_ogg(buffer.getvalue())
    assert encoded.startswith(b"OggS")
    with av.open(io.BytesIO(encoded)) as recording:
        frames = list(recording.decode(audio=0))
        assert frames and len(frames[0].layout.channels) == 2
        assert abs(sum(f.samples / f.sample_rate for f in frames) - 1) < 0.05


def test_answer_bound_capability_requires_verified_answer_and_is_single_use(monkeypatch):
    from brightwater import plivo_gateway as gateway
    from brightwater.plivo_security import create_stream_token

    cfg = config(gateway_stream_auth_mode="answer_bound_token")
    context = {"call_id": "11111111-1111-1111-1111-111111111111", "call_uuid": "22222222-2222-2222-2222-222222222222",
        "status": "answered", "answer_verified": True}

    class Store:
        async def get(self, sid):
            return context if sid == "owned-session" else None

    class Claims:
        def __init__(self):
            self.used = set()

        async def set(self, key, value, **kwargs):
            if key in self.used:
                return False
            self.used.add(key)
            return True

        async def rpush(self, *args):
            return 1

        async def ltrim(self, *args):
            return True

    admissions = []

    async def never_dial_or_process_audio(app, ws, record, settings, event):
        admissions.append(record["call_id"])
        await ws.send_json({"authenticated": True})
        await ws.close()

    monkeypatch.setattr(gateway, "run_voice", never_dial_or_process_audio)
    app = create_app(cfg)
    app.state.store, app.state.redis, app.state.tasks = Store(), Claims(), set()
    client = TestClient(app)
    token = create_stream_token(secret=cfg.gateway_token.get_secret_value(), call_id=context["call_id"], call_uuid=context["call_uuid"])
    uri = "/plivo/media/owned-session?token=" + token
    with client.websocket_connect(uri) as ws:
        assert ws.receive_json() == {"authenticated": True}
    assert admissions == [context["call_id"]]
    with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect(uri):
        pass
    assert error.value.code == 1008 and len(admissions) == 1
    app.state.redis = Claims()
    context["answer_verified"] = False
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(uri):
        pass
    assert len(admissions) == 1
    context["answer_verified"] = True
    context["status"] = "ended"
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(uri):
        pass
    assert len(admissions) == 1


def test_answer_token_mode_does_not_admit_missing_or_cross_call_credentials():
    from brightwater.plivo_security import create_stream_token

    cfg = config(gateway_stream_auth_mode="answer_bound_token")
    context = {"call_id": "11111111-1111-1111-1111-111111111111", "call_uuid": "22222222-2222-2222-2222-222222222222",
        "status": "answered", "answer_verified": True}

    class Store:
        async def get(self, sid):
            return context

    app = create_app(cfg)
    app.state.store = Store()
    client = TestClient(app)
    wrong = create_stream_token(secret=cfg.gateway_token.get_secret_value(), call_id="33333333-3333-3333-3333-333333333333", call_uuid=context["call_uuid"])
    for token in ("", "forged", wrong):
        with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect("/plivo/media/owned-session?token=" + token):
            pass
        assert error.value.code == 1008


@pytest.mark.parametrize("hold", [False, True])
def test_rejected_wire_packet_is_encrypted_and_diagnostic_hold_does_not_cut_prompt(hold):
    import asyncio
    import json
    from types import SimpleNamespace

    from pydantic import SecretStr

    from brightwater.plivo_gateway import run_voice

    raw = json.dumps({"event": "start", "sequenceNumber": "invalid", "start": {}})
    cipher = Fernet(Fernet.generate_key())
    retained, hangups, events = [], [], []

    class Socket:
        async def receive_text(self):
            return raw

        async def send_json(self, payload):
            raise AssertionError("No output audio is valid before a start event")

        async def close(self, code):
            pass

    class Broker:
        async def set(self, key, value, **kwargs):
            retained.append((key, value, kwargs))

    class Carrier:
        async def hangup(self, call_uuid):
            hangups.append(call_uuid)

    async def record(context, kind, payload, **kwargs):
        events.append(kind)

    app = SimpleNamespace(state=SimpleNamespace(carrier=Carrier(), redis=Broker(), store=SimpleNamespace(cipher=cipher)))
    context = {"call_id": "test-call", "call_uuid": "carrier-call", "sid": "owned-session"}
    cfg = SimpleNamespace(plivo_auth_id=SecretStr("test-account"), gateway_diagnostic_hold=hold)
    asyncio.run(run_voice(app, Socket(), context, cfg, record))
    assert len(retained) == 1 and retained[0][2]["ex"] == 600
    assert raw.encode() not in retained[0][1]
    assert json.loads(cipher.decrypt(retained[0][1]))["packet"] == raw
    assert events == (["turn_state"] if hold else ["failed"])
    assert hangups == ([] if hold else ["carrier-call"])


@pytest.mark.parametrize("owned", [True, False])
def test_numeric_stream_account_label_needs_authenticated_matching_stream_metadata(owned):
    import asyncio

    import httpx

    from brightwater.plivo_audio import AudioTransportError, PlivoAudioTransport
    from brightwater.plivo_client import PlivoClient, PlivoCredentials

    call_id = "11111111-1111-1111-1111-111111111111"
    stream_id = "22222222-2222-2222-2222-222222222222"
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path == f"/v1/Account/test-auth/Call/{call_id}/Stream/{stream_id}/"
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, json={"call_uuid": call_id, "stream_id": stream_id if owned else "another-stream"})

    class Socket:
        async def send_json(self, message):
            pass

        async def close(self, code):
            pass

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            carrier = PlivoClient(http, PlivoCredentials("test-auth", "not-real-token"))

            async def verify(start):
                try:
                    await carrier.stream_metadata(call_id, start["streamId"])
                    return True
                except ValueError:
                    return False

            transport = PlivoAudioTransport(Socket(), expected_call_id=call_id, expected_account_id="test-auth", verify_start=verify)
            await transport.start()
            packet = {"event": "start", "sequenceNumber": 0, "start": {"callId": call_id, "accountId": "12345678", "streamId": stream_id, "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000}}}
            if owned:
                await transport.handle_message(packet)
                await transport.wait_ready()
                assert not transport.is_closed
            else:
                with pytest.raises(AudioTransportError):
                    await transport.handle_message(packet)
            assert len(requests) == 1
            await transport.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("polite,message", [(False, None), (True, None), (False, "Your opt-out is saved.")])
def test_authenticated_stop_can_only_end_the_existing_bound_call_once(polite, message):
    from types import SimpleNamespace
    call_id = '11111111-1111-1111-1111-111111111111'
    context = {'call_id': call_id, 'call_uuid': 'carrier-owned', 'status': 'streaming', 'answer_verified': True}
    class Broker:
        def __init__(self):
            self.values = {'voice:admission:' + call_id: b'session', 'voice:active': call_id.encode()}
        async def get(self, key):
            return self.values.get(key)
        async def set(self, key, value, **kw):
            if key in self.values and kw.get('nx'):
                return False
            self.values[key] = value.encode()
            return True
    class Store:
        async def get(self, sid):
            return context if sid == 'session' else None
    stopped = []
    async def hangup(identifier):
        stopped.append(identifier)
    app = create_app(config())
    broker = Broker()
    app.state.store, app.state.redis = Store(), broker
    app.state.carrier = SimpleNamespace(hangup=hangup)
    import asyncio
    boundary = asyncio.Event()
    app.state.active_bridges = {call_id: SimpleNamespace(boundary_requested=boundary)}
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + 'a' * 40}
    assert client.post('/v1/stop', json={'call_id': call_id}).status_code == 401
    assert client.post('/v1/stop', headers=headers, json={'call_id': call_id, 'call_uuid': 'other'}).status_code == 422
    assert client.post('/v1/stop', headers=headers, json={'call_id': '22222222-2222-2222-2222-222222222222'}).status_code == 404
    broker.values['voice:active'] = b'another-call'
    assert client.post('/v1/stop', headers=headers, json={'call_id': call_id}).status_code == 409
    broker.values['voice:active'] = call_id.encode()
    context['answer_verified'] = False
    assert client.post('/v1/stop', headers=headers, json={'call_id': call_id}).status_code == 409
    context['answer_verified'] = True
    request = {'call_id': call_id, 'polite': polite, 'closing_message': message}
    result = client.post('/v1/stop', headers=headers, json=request).json()
    plays_closing = polite or message is not None
    assert result == ({'stopped': False, 'polite_closing_requested': True} if plays_closing else {'stopped': True})
    assert boundary.is_set() is plays_closing
    if plays_closing:
        assert app.state.active_bridges[call_id].closing_message == message
    assert client.post('/v1/stop', headers=headers, json={'call_id': call_id, 'polite': polite}).json()['already_requested'] is True
    assert stopped == ([] if plays_closing else ['carrier-owned'])
    context['status'] = 'ended'
    assert client.post('/v1/stop', headers=headers, json={'call_id': call_id}).json()['already_ended'] is True
    assert stopped == ([] if plays_closing else ['carrier-owned'])


def test_india_gateway_cannot_be_configured_for_customer_campaigns():
    with pytest.raises(ValueError, match='engineering-only'):
        config(gateway_campaign_enabled=True)


def test_uk_campaign_gateway_checks_main_admission_and_never_redials(monkeypatch):
    import httpx

    import brightwater.plivo_gateway as gateway
    cfg = config(gateway_country='GB', gateway_enabled=True, gateway_campaign_enabled=True,
        plivo_from_number='+442079460123', engineering_recipient='', voice_backend='elevenlabs')
    app = create_app(cfg)
    class Broker:
        def __init__(self):self.values = {}
        async def get(self,key):return self.values.get(key)
        async def set(self,key,value,**kw):
            if kw.get('nx') and key in self.values:
                return False
            self.values[key] = str(value).encode()
            return True
    class Store:
        def __init__(self):self.values = {}
        async def get(self,key):return self.values.get(key)
        async def put(self,key,value):self.values[key] = dict(value)
    class Carrier:
        def __init__(self):self.requests = 0
        async def make_call(self,**kw):
            self.requests += 1
            assert kw['to_number'] == '+447911123456'
            return 'accepted-isolated-carrier-fixture'
    class Main:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kw):
            return httpx.Response(200,json={'admitted':True,'call_id':kw['json']['call_id']},request=httpx.Request('POST',url))
    monkeypatch.setattr(gateway.httpx,'AsyncClient',Main)
    app.state.redis, app.state.store, app.state.carrier = Broker(), Store(), Carrier()
    client = TestClient(app)
    body = {'call_id':'11111111-1111-1111-1111-111111111111','purpose':'campaign',
        'phone':'+447911123456','session_token':'isolated-scoped-token','max_seconds':900}
    headers = {'Authorization':'Bearer '+cfg.gateway_token.get_secret_value()}
    assert client.post('/v1/outbound',headers=headers,json={**body,'phone':'+919876543210'}).status_code == 403
    assert client.post('/v1/outbound',headers=headers,json=body).status_code == 202
    assert client.post('/v1/outbound',headers=headers,json=body).json()['replayed'] is True
    assert app.state.carrier.requests == 1
