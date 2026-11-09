"""Pure offline tests: run pytest --noconftest tests/test_plivo_security.py."""

import base64
import hashlib
import hmac

import pytest

from brightwater.plivo_security import (
    configured_external_url,
    create_stream_token,
    v3_canonical_string,
    v3_replay_key,
    verify_stream_token,
    verify_v3_signature,
)

TOKEN = "test-plivo-token"  # Synthetic fixture, not a provider credential.
SECRET = "media-test-secret-" * 4


def signature(message, key=TOKEN):
    return base64.b64encode(
        hmac.new(key.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()


def test_post_without_query_matches_sdk_separator_vector():
    params = {"Status": "answered", "From": "+919000000000", "CallUUID": "call-123"}
    assert v3_canonical_string("POST", "https://api.example.test/answer", params) == (
        "https://api.example.test/answer?CallUUIDcall-123From+919000000000Statusanswered"
    )
    assert verify_v3_signature(
        method="POST",
        external_url="https://api.example.test/answer",
        nonce="nonce-123",
        signatures="fFYw4njIaQDMY0xNvWgqnTTAUt7PnOm7B9Rya8YZE+o=",
        auth_tokens=[TOKEN],
        params=params,
    )


def test_post_query_sorting_duplicate_values_and_blank_params():
    url = "https://api.example.test/status?b=hello%20world&a=2&a=1"
    params = [("Status", "ringing"), ("CallUUID", "call-123")]
    assert verify_v3_signature(
        method="POST",
        external_url=url,
        nonce=["nonce-123"],
        signatures="eoVl4qxu5hcIlbdJfpgSgxGMYL7cVRyIW6xQRw0oo0s=",
        auth_tokens=[TOKEN],
        params=params,
    )
    assert (
        v3_canonical_string(
            "POST", "https://api.example.test/status", [("A", "2"), ("A", "1"), ("Z", "")]
        )
        == "https://api.example.test/status?A1A2Z"
    )
    assert (
        v3_canonical_string("POST", "https://api.example.test/status")
        == "https://api.example.test/status"
    )


def test_websocket_upgrade_uses_get_and_configured_https_uri():
    assert verify_v3_signature(
        method="GET",
        external_url="https://api.example.test/stream?call=call-123",
        nonce="nonce-123",
        signatures="9ZRNG2NxPbSLHgQ/zPv3Z9kydIWJ54U5/uGwxB9qVFo=",
        auth_tokens=[TOKEN],
    )
    assert not verify_v3_signature(
        method="GET",
        external_url="wss://api.example.test/stream?call=call-123",
        nonce="nonce-123",
        signatures="9ZRNG2NxPbSLHgQ/zPv3Z9kydIWJ54U5/uGwxB9qVFo=",
        auth_tokens=[TOKEN],
    )


def test_rotated_token_signatures_and_repeated_header_lines():
    good = signature("https://api.example.test/status.nonce-123")
    wrong = signature("https://api.example.test/status.nonce-123", "old-token")
    for headers in [f"{wrong}, {good}", [wrong, good]]:
        assert verify_v3_signature(
            method="GET",
            external_url="https://api.example.test/status",
            nonce="nonce-123",
            signatures=headers,
            auth_tokens=["rotated-old-token", TOKEN],
        )


@pytest.mark.parametrize(
    "change", ["nonce", "body", "url", "token", "signature", "method", "duplicate-nonce"]
)
def test_tampered_or_ambiguous_callback_rejected(change):
    args = dict(
        method="POST",
        external_url="https://api.example.test/answer",
        nonce="nonce-123",
        signatures="fFYw4njIaQDMY0xNvWgqnTTAUt7PnOm7B9Rya8YZE+o=",
        auth_tokens=[TOKEN],
        params={"Status": "answered", "From": "+919000000000", "CallUUID": "call-123"},
    )
    if change == "nonce":
        args["nonce"] = "different"
    elif change == "body":
        args["params"]["Status"] = "completed"
    elif change == "url":
        args["external_url"] = "https://evil.example.test/answer"
    elif change == "token":
        args["auth_tokens"] = ["wrong"]
    elif change == "signature":
        args["signatures"] = "%%%"
    elif change == "method":
        args["method"] = "PUT"
    else:
        args["nonce"] = ["nonce-123", "nonce-123"]
    assert not verify_v3_signature(**args)


def test_configured_origin_does_not_consume_forwarded_host():
    assert (
        configured_external_url("https://api.example.test", "/answer", "attempt=abc%2D123")
        == "https://api.example.test/answer?attempt=abc%2D123"
    )
    for origin in [
        "http://0.0.0.0:8787",
        "https://name:secret@api.example.test",
        "https://api.example.test/path",
        "https://api.example.test?x=1",
    ]:
        with pytest.raises(ValueError):
            configured_external_url(origin, "/answer")
    with pytest.raises(ValueError):
        configured_external_url("https://api.example.test", "//evil.test/answer")
    assert v3_replay_key("https://api.example.test/answer", "n") != v3_replay_key(
        "https://api.example.test/answer", "m"
    )


def test_stream_token_is_short_lived_bound_to_both_ids_and_rotatable():
    token = create_stream_token(
        secret=SECRET, call_id="internal-123", call_uuid="plivo-456", now=1000
    )
    claims = verify_stream_token(
        token=token, secret=SECRET, call_id="internal-123", call_uuid="plivo-456", now=1000
    )
    assert claims and claims.expires_at == 1120 and len(claims.session_id) == 32
    assert verify_stream_token(
        token=token, secret=SECRET, call_id="internal-123", call_uuid="plivo-456", now=1119
    )
    for changes in [
        {"now": 1120},
        {"now": 999},
        {"call_id": "other"},
        {"call_uuid": "other"},
        {"secret": "rotated-secret" * 4},
        {"token": token + "x"},
    ]:
        args = dict(
            token=token, secret=SECRET, call_id="internal-123", call_uuid="plivo-456", now=1000
        )
        args.update(changes)
        assert verify_stream_token(**args) is None


def test_token_limits_and_bad_inputs_fail_closed():
    for value in [0, 601, True]:
        with pytest.raises(ValueError):
            create_stream_token(secret=SECRET, call_id="a", call_uuid="b", ttl_seconds=value)
    with pytest.raises(ValueError):
        create_stream_token(secret="short", call_id="a", call_uuid="b")
    assert (
        verify_stream_token(token="not-a-token", secret=SECRET, call_id="a", call_uuid="b") is None
    )
    assert not verify_v3_signature(
        method="GET",
        external_url="https://api.example.test",
        nonce="a,b",
        signatures="bad",
        auth_tokens=[TOKEN],
    )



def test_both_published_stream_hmac_formats_require_account_secret_and_exact_uri():
    from brightwater.plivo_security import verify_stream_signature
    url = "https://voice.example.test/plivo/media/session?token=application-token"
    nonce = "opaque-test-nonce"
    manual = signature("GET" + url + nonce)
    standard = signature(url + "." + nonce)
    assert verify_stream_signature(external_url=url, nonce=nonce, signatures=manual, auth_tokens=[TOKEN]) == "stream-reference"
    assert verify_stream_signature(external_url=url, nonce=nonce, signatures=standard, auth_tokens=[TOKEN]) == "v3-sdk"
    for changed_url, changed_nonce, changed_key in [(url + "x", nonce, TOKEN), (url, "other", TOKEN), (url, nonce, "wrong-key")]:
        assert verify_stream_signature(external_url=changed_url, nonce=changed_nonce, signatures=manual, auth_tokens=[changed_key]) is None
    assert verify_stream_signature(external_url=url, nonce=nonce, signatures=None, auth_tokens=[TOKEN]) is None
