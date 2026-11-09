"""Real outbound adapter. No dummy success path exists."""

import asyncio
import json

from brightwater.config import settings


async def initiate(call_id: str, phone: str, scoped_token: str) -> str:
    from google.protobuf.duration_pb2 import Duration
    from livekit import api

    cfg = settings()
    if not cfg.dialing_enabled or cfg.environment in {"shadow", "showcase", "test"}:
        raise RuntimeError("Outbound network effects disabled")
    room = f"bw-{call_id}"
    metadata = json.dumps({"call_id": call_id, "session_token": scoped_token, "release_id": cfg.release_id})
    # The room ID is stable for reconciliation, but SIP initiation itself is NOT
    # assumed idempotent. A timeout is quarantined by the caller, never redialled.
    async with api.LiveKitAPI(cfg.livekit_url, cfg.livekit_api_key.get_secret_value(),
                             cfg.livekit_api_secret.get_secret_value()) as client:
        await client.room.create_room(api.CreateRoomRequest(
            name=room, max_participants=2,
            agents=[api.RoomAgentDispatch(agent_name=cfg.voice_agent_name, metadata=metadata)]))
        # Never ring the customer while the speaking worker is still cold.
        for _ in range(20):
            participants = await client.room.list_participants(api.ListParticipantsRequest(room=room))
            if any(p.kind == api.ParticipantInfo.AGENT and p.attributes.get("bw.ready") == "true"
                   and p.attributes.get("bw.call_id") == call_id for p in participants.participants):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("Voice worker did not become ready before dial admission")
        result = await client.sip.create_sip_participant(api.CreateSIPParticipantRequest(
            sip_trunk_id=cfg.livekit_outbound_trunk_id,
            sip_call_to=phone, room_name=room, participant_identity=f"customer-{call_id}",
            participant_name="Customer", hide_phone_number=True, wait_until_answered=False,
            participant_attributes={"bw.call_id": call_id},
            ringing_timeout=Duration(seconds=50), max_call_duration=Duration(seconds=900),
        ), timeout=10)
        return result.sip_call_id
