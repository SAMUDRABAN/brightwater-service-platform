import hashlib
import os
import secrets
from pathlib import Path

import pytest
from dotenv import dotenv_values

env_file = Path(os.getenv("BW_TEST_ENV_FILE", Path(__file__).resolve().parents[1] / ".env.test"))
if env_file.exists():
    os.environ.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})

from brightwater import models as m  # noqa: E402
from brightwater.config import settings  # noqa: E402
from brightwater.db import Base, engine, session  # noqa: E402
from brightwater.policy import now  # noqa: E402
from brightwater.seed import seed  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    cfg = settings()
    assert cfg.environment == "test" and "/brightwater_test" in cfg.database_url.get_secret_value(), "Refusing to reset a non-test database"
    Base.metadata.drop_all(engine())
    Base.metadata.create_all(engine())
    with session() as db, db.begin():
        seed(db)
    yield


def make_call(db, customer_id="BW-1041", verified=True):
    dest = m.Destination(customer_id=customer_id, phone="+447911123456", enabled=True,
                         consent_reference="Offline integration-test fixture; never dial")
    db.add(dest)
    db.flush()
    token = secrets.token_urlsafe(40)
    call = m.Call(customer_id=customer_id, destination_id=dest.id, year=2026, attempt=1,
                  request_key=m.uid(), state="in_progress", time_band="midday",
                  dispatched_at=now(), identity_verified=verified, conversation=verified,
                  session_token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(call)
    db.add(m.CampaignContact(customer_id=customer_id, year=2026))
    db.flush()
    return call, token
