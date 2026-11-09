"""Plivo V3 verification and application-owned media-session credentials.

V3 canonicalization follows Plivo's official Python SDK, including its query
sorting and separators, not the contradictory manual streaming-doc example:
https://github.com/plivo/plivo-python/blob/master/plivo/utils/signature_v3.py
https://www.plivo.com/docs/voice/concepts/signature-validation
Encrypted WebSocket upgrades are signed GET requests with an HTTPS URI:
https://github.com/plivo/plivo-stream-sdk-node/blob/main/src/index.ts

Pass a configured public URL; never synthesize it from untrusted Host/forwarded
headers. A verified signature alone does not prevent replay. Handlers must use
durable event deduplication, call-state checks and atomic media-session claims.
Stream tokens below are our protocol, not a Plivo-authentication replacement.
Do not log tokens, nonces, signature headers, form bodies or credential values.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse

type HeaderValue = str | Sequence[str] | None
type FormParams = Mapping[str, str | Sequence[str]] | Sequence[tuple[str, str]] | None


def configured_external_url(origin: str, path: str, raw_query: str = "") -> str:
    """Build the expected external HTTPS URL from trusted origin + known route.

    raw_query is the original ASCII query string without '?', not a decoded or
    re-encoded request.query_params mapping. Origin must come from configuration.
    """
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in origin)
    ):
        raise ValueError("Invalid configured public HTTPS origin")
    # Validate port, but preserve any explicitly configured port in the signature.
    _ = parsed.port
    if (
        not path.startswith("/")
        or path.startswith("//")
        or any(c in path for c in "?#;\r\n")
        or "#" in raw_query
        or any(ord(c) < 32 or ord(c) > 126 for c in raw_query)
    ):
        raise ValueError("Invalid callback route or query")
    return f"https://{parsed.netloc}{path}" + (f"?{raw_query}" if raw_query else "")


def _form_map(params: FormParams) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if params is None:
        return result
    pairs = params.items() if isinstance(params, Mapping) else params
    for key, value in pairs:
        if not isinstance(key, str) or not key:
            raise ValueError("Form names must be strings")
        values = [value] if isinstance(value, str) else list(value)
        if not all(isinstance(item, str) for item in values):
            raise ValueError("Form values must be strings")
        result.setdefault(key, []).extend(values)
    if len(result) > 256 or sum(len(k) + sum(map(len, v)) for k, v in result.items()) > 65536:
        raise ValueError("Form parameters exceed verification limit")
    return result


def v3_canonical_string(method: str, external_url: str, params: FormParams = None) -> str:
    """Return the SDK-compatible URL/form string before the '.nonce' suffix.

    Case-sensitive key order and sorted repeated values match the official SDK.
    Values are decoded form/query text, not URL-encoded a second time. GET input
    parameters belong in external_url's original query, not in params.
    """
    method = method.upper()
    if method not in {"GET", "POST"}:
        raise ValueError("Only Plivo GET and POST callbacks are supported")
    if len(external_url) > 8192:
        raise ValueError("Callback URL exceeds verification limit")
    parsed = urlparse(external_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.params
        or any(c.isspace() for c in external_url)
    ):
        raise ValueError("Expected configured external HTTPS callback URL")
    _ = parsed.port
    body = _form_map(params)
    if method == "GET" and body:
        raise ValueError("GET parameters must be in the original URL query")
    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=256)
    query_string = "&".join(
        f"{key}={value}" for key in sorted(query) for value in sorted(query[key])
    )
    base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if query_string or body:
        base += "?" + query_string
    if query_string and body:
        base += "."
    if method == "POST":
        base += "".join(f"{key}{value}" for key in sorted(body) for value in sorted(body[key]))
    return base


def _single_nonce(value: HeaderValue) -> str | None:
    values = [value] if isinstance(value, str) else list(value or [])
    if len(values) != 1 or not isinstance(values[0], str):
        return None
    nonce = values[0]
    # Plivo documents one opaque nonce, not comma-separated nonce alternatives.
    return (
        nonce
        if 0 < len(nonce) <= 256 and all(33 <= ord(c) <= 126 and c != "," for c in nonce)
        else None
    )


def verify_v3_signature(
    *,
    method: str,
    external_url: str,
    nonce: HeaderValue,
    signatures: HeaderValue,
    auth_tokens: Sequence[str],
    params: FormParams = None,
) -> bool:
    """Verify standard or MA V3 header using the corresponding account token(s).

    signatures accepts the documented comma-separated signature list, and also
    repeated HTTP header lines supplied as a sequence. Nonce must be singular.
    Pair X-Plivo-Signature-V3 with entity-account tokens OR the MA header with
    main-account tokens; do not silently mix account identity policies.
    """
    try:
        selected_nonce = _single_nonce(nonce)
        values = [signatures] if isinstance(signatures, str) else list(signatures or [])
        if not selected_nonce or not values or len(values) > 8:
            return False
        if not all(isinstance(value, str) for value in values):
            return False
        candidates = [item.strip() for value in values for item in value.split(",")]
        if len(candidates) > 8 or any(len(item) > 128 for item in candidates):
            return False
        decoded = []
        for item in candidates:
            try:
                signature = base64.b64decode(item, validate=True)
            except (ValueError, binascii.Error):
                continue
            if len(signature) == 32:
                decoded.append(signature)
        if isinstance(auth_tokens, str) or not 0 < len(auth_tokens) <= 8:
            return False
        message = f"{v3_canonical_string(method, external_url, params)}.{selected_nonce}".encode()
        matched = False
        for token in auth_tokens:
            if not isinstance(token, str) or not token or len(token) > 4096:
                return False
            expected = hmac.digest(token.encode(), message, "sha256")
            for candidate in decoded:
                matched = hmac.compare_digest(expected, candidate) or matched
        return matched
    except (ValueError, TypeError, UnicodeError):
        return False


def v3_replay_key(external_url: str, nonce: str) -> str:
    """Opaque deduplication key; the caller must atomically persist/check it.

    No nonce age is invented: the documented V3 nonce has no timestamp contract.
    A duplicate valid callback may be acknowledged without repeating its effects.
    """
    return hashlib.sha256(f"plivo-v3\0{external_url}\0{nonce}".encode()).hexdigest()


@dataclass(frozen=True)
class StreamClaims:
    call_id: str
    call_uuid: str
    issued_at: int
    expires_at: int
    session_id: str


def _stream_key(secret: str) -> bytes:
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise ValueError("A separate strong media-session signing secret is required")
    return hmac.digest(secret.encode(), b"brightwater-plivo-stream-v1", "sha256")


def _id(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def create_stream_token(
    *, secret: str, call_id: str, call_uuid: str, ttl_seconds: int = 120, now: int | None = None
) -> str:
    """Mint an application token after a signed answer callback binds CallUUID.

    It contains identifiers only, no phone/name/secret. Prefer Stream extraHeaders
    plus an authenticated upgrade over a bearer query token exposed to URL logs.
    """
    if (
        not _id(call_id)
        or not _id(call_uuid)
        or type(ttl_seconds) is not int
        or not 1 <= ttl_seconds <= 600
    ):
        raise ValueError("Invalid media-session identifiers or lifetime")
    issued = int(time.time()) if now is None else now
    if type(issued) is not int or issued < 0:
        raise ValueError("Invalid token clock")
    data = {
        "v": 1,
        "purpose": "plivo-stream",
        "call_id": call_id,
        "call_uuid": call_uuid,
        "iat": issued,
        "exp": issued + ttl_seconds,
        "jti": secrets.token_hex(16),
    }
    payload = _b64(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
    signature = _b64(hmac.digest(_stream_key(secret), payload.encode(), "sha256"))
    return f"{payload}.{signature}"


def verify_stream_token(
    *, token: str, secret: str, call_id: str, call_uuid: str, now: int | None = None
) -> StreamClaims | None:
    """Verify signature, bounded absolute expiry and BOTH authoritative IDs.

    After verification, atomically claim session_id and compare incoming start's
    callId with claims.call_uuid before processing audio or creating AI sessions.
    This helper is stateless and cannot make a token single-use on its own.
    """
    try:
        if (
            not isinstance(token, str)
            or len(token) > 2048
            or not _id(call_id)
            or not _id(call_uuid)
        ):
            return None
        parts = token.split(".")
        if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
            return None
        payload, signature = parts
        expected = _b64(hmac.digest(_stream_key(secret), payload.encode(), "sha256"))
        if not hmac.compare_digest(expected, signature):
            return None
        body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        at = int(time.time()) if now is None else now
        if not isinstance(body, dict) or type(at) is not int:
            return None
        if (
            body.get("v") != 1
            or body.get("purpose") != "plivo-stream"
            or not isinstance(body.get("call_id"), str)
            or not isinstance(body.get("call_uuid"), str)
            or not hmac.compare_digest(body["call_id"], call_id)
            or not hmac.compare_digest(body["call_uuid"], call_uuid)
            or type(body.get("iat")) is not int
            or type(body.get("exp")) is not int
            or not body["iat"] <= at < body["exp"]
            or not 1 <= body["exp"] - body["iat"] <= 600
            or not isinstance(body.get("jti"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", body["jti"])
        ):
            return None
        return StreamClaims(
            body["call_id"], body["call_uuid"], body["iat"], body["exp"], body["jti"]
        )
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return None


def verify_stream_signature(*, external_url: str, nonce: HeaderValue, signatures: HeaderValue,
                            auth_tokens: Sequence[str]) -> str | None:
    """Accept Plivo's two published, fully authenticated upgrade constructions.

    Core V3 SDK and Stream Protocol Reference currently publish different HMAC
    inputs. Both bind the same configured complete HTTPS URI and nonce to the
    secret account token. This is not an unsigned fallback; the separate
    call-bound, expiring application token remains mandatory at the gateway.
    """
    if verify_v3_signature(method="GET", external_url=external_url, nonce=nonce,
                           signatures=signatures, auth_tokens=auth_tokens):
        return "v3-sdk"
    try:
        v3_canonical_string("GET", external_url)  # Strict configured-URI validation.
        selected = _single_nonce(nonce)
        values = [signatures] if isinstance(signatures, str) else list(signatures or [])
        if not selected or not 0 < len(values) <= 8 or not 0 < len(auth_tokens) <= 8 or isinstance(auth_tokens, str):
            return None
        if not all(isinstance(value, str) for value in values):
            return None
        candidates = [item.strip() for value in values for item in value.split(",")]
        if len(candidates) > 8 or any(len(item) > 128 for item in candidates):
            return None
        matched = False
        for key in auth_tokens:
            if not isinstance(key, str) or not key or len(key) > 4096:
                return None
            expected = base64.b64encode(hmac.digest(key.encode(), f"GET{external_url}{selected}".encode(), "sha256")).decode()
            for candidate in candidates:
                matched = hmac.compare_digest(expected, candidate) or matched
        return "stream-reference" if matched else None
    except (ValueError, TypeError, UnicodeError):
        return None
