from fastapi.testclient import TestClient


def test_dev_user_idempotent(client: TestClient):
    r1 = client.post("/api/v1/users/dev")
    r2 = client.post("/api/v1/users/dev")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["user_key"] == "dev"
