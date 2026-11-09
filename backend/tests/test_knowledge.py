from conftest import make_call
from fastapi.testclient import TestClient

from brightwater.api import app
from brightwater.db import session


def test_public_knowledge_works_before_identity_without_customer_disclosure():
    with session() as db, db.begin():
        _, token = make_call(db, verified=False)
    client = TestClient(app)
    response = client.get("/runtime/knowledge", params={"query": "office hours and payment prices"},
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["approved_services"]["combined"]["price_pence"] == 14500
    assert data["office_callback_number"] is None
    assert "Helen" not in response.text and "Albert Road" not in response.text


def test_unknown_knowledge_does_not_invent_an_answer():
    with session() as db, db.begin():
        _, token = make_call(db, verified=False)
    response = TestClient(app).get("/runtime/knowledge", params={"query": "cryptocurrency investment"},
                                    headers={"Authorization": f"Bearer {token}"})
    assert response.json()["answers"] == []
    assert response.json()["fallback"]
