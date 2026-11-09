import pytest
from conftest import make_call
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from brightwater.api import app
from brightwater.config import settings
from brightwater.db import session
from brightwater.media import read_recording
from brightwater.policy import Rejected


@pytest.fixture
def storage(monkeypatch, tmp_path):
    cfg = settings()
    monkeypatch.setattr(cfg, "media_root", tmp_path)
    monkeypatch.setattr(cfg, "media_encryption_key", SecretStr(Fernet.generate_key().decode()))
    return tmp_path


def test_recording_is_encrypted_and_requires_separate_upload_and_playback_credentials(storage):
    # Deliberately synthetic bytes test storage/auth, not decodability or quality.
    payload = b"OggS" + b"offline-storage-fixture" * 10
    with session() as db, db.begin():
        call, _ = make_call(db)
        call_id = call.id
    cfg, client = settings(), TestClient(app)
    endpoint = f"/internal/calls/{call_id}/recording"
    operator = {"Authorization": "Bearer " + cfg.operator_token.get_secret_value()}
    runtime = {"Authorization": "Bearer " + cfg.runtime_token.get_secret_value(), "Content-Type": "audio/ogg"}
    assert client.post(endpoint, content=payload, headers=operator).status_code == 401
    assert client.post(endpoint, content=payload, headers=runtime).status_code == 200
    assert client.post(endpoint, content=payload, headers=runtime).status_code == 200
    path = next(storage.glob("*.enc"))
    assert payload not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    playback = f"/v1/calls/{call_id}/recording"
    assert client.get(playback).status_code == 401
    assert client.get(playback, headers=runtime).status_code == 401
    response = client.get(playback, headers=operator)
    assert response.status_code == 200 and response.content == payload
    assert response.headers["cache-control"] == "no-store"
    path.write_bytes(b"corrupt cipher")
    assert client.get(playback, headers=operator).status_code == 503


def test_recording_path_traversal_is_rejected_before_filesystem_access(storage):
    with pytest.raises(Rejected) as caught:
        read_recording("../../environment")
    assert caught.value.code == "invalid_recording_key"


def test_different_recording_cannot_replace_attached_evidence(storage):
    with session() as db, db.begin():
        call, _ = make_call(db)
        call_id = call.id
    cfg, client = settings(), TestClient(app)
    headers = {"Authorization": "Bearer " + cfg.runtime_token.get_secret_value(), "Content-Type": "audio/ogg"}
    url = f"/internal/calls/{call_id}/recording"
    assert client.post(url, content=b"OggS" + b"first-fixture" * 10, headers=headers).status_code == 200
    assert client.post(url, content=b"OggS" + b"second-fixture" * 10, headers=headers).status_code == 409
