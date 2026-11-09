"""Small real Plivo REST client. Initiation is never blindly retried."""
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS


class PlivoRequestUncertain(RuntimeError):
    """A carrier may have accepted the operation; reconcile before retrying."""


@dataclass(frozen=True)
class PlivoCredentials:
    auth_id: str = field(repr=False)
    auth_token: str = field(repr=False)


class PlivoClient:
    def __init__(self, client: httpx.AsyncClient, credentials: PlivoCredentials):
        self.client, self.credentials = client, credentials
        self.base = 'https://api.plivo.com/v1/Account/' + quote(credentials.auth_id, safe='')

    async def request(self, method, path, *, payload=None):
        try:
            response = await self.client.request(method, self.base + path, json=payload,
                auth=(self.credentials.auth_id, self.credentials.auth_token), timeout=12)
        except httpx.HTTPError:
            raise PlivoRequestUncertain('Carrier request acknowledgement unavailable') from None
        if not response.is_success:
            raise PlivoRequestUncertain('Carrier operation returned HTTP ' + str(response.status_code))
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise PlivoRequestUncertain('Carrier acknowledgement was malformed') from None

    async def make_call(self, *, from_number, to_number, answer_url, hangup_url, max_seconds=ATTENDED_CALL_MAX_SECONDS):
        if not 30 <= max_seconds <= ATTENDED_CALL_MAX_SECONDS:
            raise ValueError('Explicit bounded call duration required')
        result = await self.request('POST', '/Call/', payload={
            'from': from_number, 'to': to_number, 'answer_url': answer_url, 'answer_method': 'POST',
            'hangup_url': hangup_url, 'hangup_method': 'POST', 'time_limit': max_seconds, 'ring_timeout': 30})
        identifier = result.get('request_uuid')
        if not isinstance(identifier, str) or not identifier:
            raise PlivoRequestUncertain('Carrier request UUID missing; do not redial')
        return identifier

    async def hangup(self, call_uuid):
        if not call_uuid:
            raise ValueError('A single explicit carrier call ID is mandatory')
        await self.request('DELETE', '/Call/' + quote(call_uuid, safe='') + '/')

    async def recording_metadata(self, recording_id, *, expected_call_uuid):
        if not recording_id or not expected_call_uuid:
            raise ValueError('Recording and expected call IDs required')
        result = await self.request('GET', '/Recording/' + quote(recording_id, safe='') + '/')
        if result.get('call_uuid') != expected_call_uuid or result.get('recording_id') != recording_id:
            raise ValueError('Recording does not belong to the bound call')
        return result


    async def stream_metadata(self, call_uuid, stream_id):
        from uuid import UUID
        UUID(call_uuid)
        UUID(stream_id)
        # This account-authenticated, read-only lookup binds the received stream
        # to the already verified call without equating internal/public account IDs.
        response = await self.client.get(self.base + '/Call/' + quote(call_uuid, safe='') + '/Stream/' + quote(stream_id, safe='') + '/',
            auth=(self.credentials.auth_id, self.credentials.auth_token), timeout=3)
        response.raise_for_status()
        result = response.json()
        if result.get('call_uuid') != call_uuid or result.get('stream_id') != stream_id:
            raise ValueError('Carrier stream ownership mismatch')
        return result
