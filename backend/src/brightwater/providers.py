"""One acknowledged campaign carrier request; no legacy voice fallback or retry."""
import httpx

from brightwater.config import settings


async def initiate(call_id: str, phone: str, scoped_token: str) -> str:
    from brightwater.campaign import configuration_issues
    from brightwater.policy import uk_phone
    cfg = settings()
    if not cfg.dialing_enabled or cfg.environment in {"shadow", "showcase", "test"} or configuration_issues(cfg):
        raise RuntimeError("Customer campaign route is not qualified or enabled")
    uk_phone(phone)
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.post(cfg.campaign_gateway_url.rstrip("/") + "/v1/outbound",
            headers={"Authorization": "Bearer " + cfg.campaign_gateway_token.get_secret_value()},
            json={"call_id": call_id, "phone": phone, "session_token": scoped_token,
                  "purpose": "campaign", "max_seconds": 900})
        response.raise_for_status()
        identifier = response.json()["request_uuid"]
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError("Carrier acknowledgement missing; reconcile without redial")
    from brightwater.managed.startup import prepare
    await prepare(call_id)
    return identifier
