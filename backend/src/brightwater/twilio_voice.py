"""Twilio callbacks and media framing for the managed UK voice gateway."""

import base64
import hashlib
import hmac
import json
import re
from urllib.parse import parse_qsl
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException

CALL_SID = re.compile(r"CA[0-9a-fA-F]{32}")
RECORDING_SID = re.compile(r"RE[0-9a-fA-F]{32}")


def valid_signature(url, fields, signature, token):
    if not signature or not token:
        return False
    value = url + "".join(key + fields[key] for key in sorted(fields))
    expected = base64.b64encode(hmac.new(token.encode(), value.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


async def signed_form(request, cfg):
    if request.url.query or not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raise HTTPException(400)
    raw = await request.body()
    if len(raw) > 16384:
        raise HTTPException(413)
    try:
        pairs = parse_qsl(raw.decode(), keep_blank_values=True, strict_parsing=True, max_num_fields=96)
    except (ValueError, UnicodeError):
        raise HTTPException(400) from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise HTTPException(400)
    if not valid_signature(cfg.gateway_origin + request.url.path, fields,
                           request.headers.get("x-twilio-signature"), cfg.twilio_auth_token.get_secret_value()):
        raise HTTPException(403)
    if fields.get("AccountSid") != cfg.twilio_account_sid.get_secret_value():
        raise HTTPException(403)
    return fields


def stream_xml(origin, sid):
    root = Element("Response")
    SubElement(SubElement(root, "Connect"), "Stream", url="wss://" + origin.removeprefix("https://") + "/twilio/media/" + sid)
    SubElement(root, "Hangup")
    return tostring(root)


class TwilioClient:
    def __init__(self, http, account_sid, auth_token, origin):
        self.http = http
        self.auth = (account_sid, auth_token)
        self.base = "https://api.twilio.com/2010-04-01/Accounts/" + account_sid
        self.origin = origin

    async def make_call(self, *, sid, from_number, to_number, max_seconds):
        data = {
            "From": from_number, "To": to_number, "Url": self.origin + "/twilio/answer/" + sid,
            "StatusCallback": self.origin + "/twilio/status/" + sid, "StatusCallbackEvent": "completed",
            "Record": "true", "RecordingChannels": "dual",
            "RecordingStatusCallback": self.origin + "/twilio/recording/" + sid,
            "RecordingStatusCallbackEvent": "in-progress completed absent",
            "Timeout": 30, "TimeLimit": max_seconds,
        }
        response = await self.http.post(self.base + "/Calls.json", auth=self.auth, data=data, timeout=10)
        response.raise_for_status()
        call_sid = response.json()["sid"]
        if not CALL_SID.fullmatch(call_sid):
            raise ValueError("Invalid Twilio call identity")
        return call_sid

    async def hangup(self, call_sid):
        if not CALL_SID.fullmatch(call_sid):
            raise ValueError("Invalid Twilio call identity")
        r = await self.http.post(self.base + "/Calls/" + call_sid + ".json", auth=self.auth,
                                 data={"Status": "completed"}, timeout=6)
        r.raise_for_status()

    async def recording(self, recording_sid, call_sid, limit):
        if not RECORDING_SID.fullmatch(recording_sid) or not CALL_SID.fullmatch(call_sid):
            raise ValueError("Invalid Twilio recording identity")
        url = self.base + "/Recordings/" + recording_sid
        meta = await self.http.get(url + ".json", auth=self.auth, timeout=8)
        meta.raise_for_status()
        info = meta.json()
        if info["call_sid"] != call_sid or info["account_sid"] != self.auth[0] or info["status"] != "completed":
            raise ValueError("Twilio recording identity does not match the call")
        data = bytearray()
        async with self.http.stream("GET", url + ".wav", auth=self.auth, timeout=20) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Recording size bound exceeded")
        return bytes(data)


class TwilioMedia:
    """Translate authenticated Twilio frames to the existing paced μ-law transport."""

    def __init__(self, socket):
        self.socket = socket
        self.stream = None
        self.clear_marker = None
        self.clear_count = 0

    async def receive_text(self):
        while True:
            raw = await self.socket.receive_text()
            if len(raw) > 65536:
                raise ValueError("Twilio frame too large")
            msg = json.loads(raw)
            kind = msg["event"]
            if kind == "connected":
                if self.stream or msg.get("protocol") != "Call":
                    raise ValueError("Unexpected Twilio protocol")
                continue
            stream = msg["streamSid"]
            if not re.fullmatch(r"MZ[0-9a-fA-F]{32}", stream):
                raise ValueError("Invalid Twilio stream identity")
            sequence = int(msg["sequenceNumber"])
            event = {"event": kind, "sequenceNumber": sequence, "streamId": stream}
            if kind == "start":
                start = msg["start"]
                fmt = start["mediaFormat"]
                if self.stream or start["streamSid"] != stream or fmt.get("channels") != 1:
                    raise ValueError("Invalid Twilio stream start")
                self.stream = stream
                event["start"] = {
                    "callId": start["callSid"], "accountId": start["accountSid"], "streamId": stream,
                    "mediaFormat": {"encoding": fmt["encoding"], "sampleRate": fmt["sampleRate"]},
                }
            elif kind == "mark":
                name = msg["mark"]["name"]
                if self.clear_marker is not None and name == self.clear_marker:
                    self.clear_marker = None
                    event["event"] = "clearedAudio"
                else:
                    event.update(event="playedStream", name=name)
            elif kind == "media":
                event["media"] = msg["media"]
            elif kind not in {"stop", "dtmf"}:
                raise ValueError("Unexpected Twilio stream event")
            return json.dumps(event)

    async def send_json(self, msg):
        kind = msg["event"]
        if not self.stream:
            raise ValueError("Twilio stream not bound")
        if kind == "playAudio":
            await self.socket.send_json({"event": "media", "streamSid": self.stream,
                                         "media": {"payload": msg["media"]["payload"]}})
        elif kind == "checkpoint":
            await self.socket.send_json({"event": "mark", "streamSid": self.stream, "mark": {"name": msg["name"]}})
        elif kind == "clearAudio":
            self.clear_count += 1
            self.clear_marker = f"twilio-clear-{self.clear_count}"
            await self.socket.send_json({"event": "clear", "streamSid": self.stream})
            # Twilio acknowledges clear by returning outstanding marks. A new
            # marker after clear fences those old receipts from fresh playback.
            await self.socket.send_json({"event": "mark", "streamSid": self.stream, "mark": {"name": self.clear_marker}})
        else:
            raise ValueError("Unexpected outgoing Twilio stream event")

    async def close(self, code):
        await self.socket.close(code=code)


def install_twilio(app, cfg, event, run_voice):
    import asyncio
    import time

    from fastapi import Request, WebSocket
    from fastapi.responses import Response

    account = cfg.twilio_account_sid.get_secret_value()
    token = cfg.twilio_auth_token.get_secret_value()
    caller_id = cfg.twilio_from_number.get_secret_value()

    async def bound(sid, fields, *, check_numbers):
        context = await app.state.store.get(sid)
        actual = fields.get("CallSid", "")
        if not context or context["purpose"] != "campaign" or not CALL_SID.fullmatch(actual):
            raise HTTPException(403)
        if check_numbers and (fields.get("From") != caller_id or fields.get("To") != context["phone"]):
            raise HTTPException(403)
        if context.get("request_uuid") not in (None, actual):
            raise HTTPException(403)
        await app.state.redis.set("voice:bind:" + sid, actual, nx=True, ex=86400)
        if await app.state.redis.get("voice:bind:" + sid) != actual.encode():
            raise HTTPException(403)
        return context, actual

    @app.post("/twilio/answer/{sid}")
    async def answer(sid: str, request: Request):
        fields = await signed_form(request, cfg)
        async with app.state.redis.lock("voice:twilio-state:" + sid, timeout=10, blocking_timeout=2):
            context, actual = await bound(sid, fields, check_numbers=True)
            if context.get("status") == "ended" or time.time() - context["created"] > 90:
                raise HTTPException(410)
            context.update(call_uuid=actual, request_uuid=actual, status="answered",
                           answer_verified=True, answer_callback_at=time.time())
            await app.state.store.put(sid, context)
        return Response(stream_xml(cfg.gateway_origin, sid), media_type="application/xml")

    @app.post("/twilio/status/{sid}")
    async def status(sid: str, request: Request):
        fields = await signed_form(request, cfg)
        state = fields.get("CallStatus")
        if state not in {"completed", "busy", "no-answer", "failed", "canceled"}:
            raise HTTPException(400)
        async with app.state.redis.lock("voice:twilio-state:" + sid, timeout=10, blocking_timeout=2):
            context, actual = await bound(sid, fields, check_numbers=True)
            context.update(call_uuid=actual, request_uuid=actual, status="ended")
            await app.state.store.put(sid, context)
        await event(context, "ended", {"carrier_call_uuid": actual, "hangup_cause": state,
                    "source": "signed_twilio_status", "carrier_answered": state == "completed"},
                    event_id="twilio-ended:" + actual)
        await app.state.redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end return 0",
                                   1, "voice:active", context["call_id"])
        return {"accepted": True}

    @app.post("/twilio/recording/{sid}")
    async def recording(sid: str, request: Request):
        fields = await signed_form(request, cfg)
        context, actual = await bound(sid, fields, check_numbers=False)
        rec, state = fields.get("RecordingSid", ""), fields.get("RecordingStatus")
        if not RECORDING_SID.fullmatch(rec) or state not in {"in-progress", "completed", "absent"}:
            raise HTTPException(400)
        if state == "absent":
            return {"accepted": True}
        key = "voice:recording-id:" + sid
        await app.state.redis.set(key, rec, nx=True, ex=86400)
        if await app.state.redis.get(key) != rec.encode():
            raise HTTPException(409)
        if state == "completed" and await app.state.redis.set("voice:recording-job:" + sid, "queued", nx=True, ex=86400):
            # The signed recording callback can precede the answer/status write.
            # Carry the independently bound carrier ID via the Redis binding.
            await app.state.redis.rpush("voice:recordings", sid)
        return {"accepted": True}

    @app.websocket("/twilio/media/{sid}")
    async def media(ws: WebSocket, sid: str):
        context = await app.state.store.get(sid)
        url = cfg.gateway_origin + ws.url.path
        signature = ws.headers.get("x-twilio-signature")
        if (ws.url.query or not context or context.get("status") != "answered"
            or not context.get("answer_verified")
            or not any(valid_signature(u, {}, signature, token) for u in (url, url + "/",
                       url.replace("https://", "wss://", 1), url.replace("https://", "wss://", 1) + "/"))):
            await ws.close(code=1008)
            return
        if not await app.state.redis.set("voice:media:" + sid, "twilio", nx=True, ex=86400):
            await ws.close(code=1008)
            return
        await ws.accept()
        task = asyncio.current_task()
        app.state.tasks.add(task)
        try:
            await run_voice(app, TwilioMedia(ws), context, cfg, event, account_id=account)
        finally:
            app.state.tasks.discard(task)
