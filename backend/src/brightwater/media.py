"""Bounded encrypted recording store; never expose a filesystem path as a URL."""

import hashlib
import os
import re

from cryptography.fernet import Fernet, InvalidToken

from brightwater.call_limits import MAX_STORED_RECORDING_BYTES
from brightwater.config import settings
from brightwater.policy import Rejected

MAX_RECORDING_BYTES = MAX_STORED_RECORDING_BYTES


def cipher():
    key = settings().media_encryption_key.get_secret_value()
    if not key:
        raise Rejected("media_unconfigured", "Encrypted recording storage is not configured", 503)
    return Fernet(key.encode())


def store_recording(content: bytes) -> str:
    if not content.startswith(b"OggS") or len(content) < 64:
        raise Rejected("invalid_recording", "An Ogg session recording is required", 422)
    if len(content) > MAX_RECORDING_BYTES:
        raise Rejected("recording_too_large", "Recording exceeds the upload limit", 413)
    encrypted = cipher().encrypt(content)
    key = hashlib.sha256(content).hexdigest() + ".ogg.enc"
    root = settings().media_root
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Atomic rename means readers never see a partially written ciphertext.
    temporary = root / (key + "." + os.urandom(12).hex() + ".tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, root / key)
    finally:
        temporary.unlink(missing_ok=True)
    return key


def read_recording(key: str) -> bytes:
    if not re.fullmatch(r"[a-f0-9]{64}\.ogg\.enc", key):
        raise Rejected("invalid_recording_key", "Recording reference is invalid", 404)
    try:
        content = cipher().decrypt((settings().media_root / key).read_bytes())
    except FileNotFoundError:
        raise Rejected("recording_unavailable", "Recording is not available", 404) from None
    except InvalidToken:
        raise Rejected("recording_integrity", "Recording could not be authenticated", 503) from None
    if hashlib.sha256(content).hexdigest() != key[:64]:
        raise Rejected("recording_integrity", "Recording digest does not match", 503)
    return content
