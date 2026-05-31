import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["deterministic"] is True


def test_auth_config_route_is_public():
    client = TestClient(app)
    response = client.get("/v1/auth/config")
    assert response.status_code == 200
    assert response.json()["provider"] == "supabase"


def test_protected_mutation_requires_bearer_token():
    client = TestClient(app)
    response = client.post(
        "/v1/memory/delete",
        json={"user_id": "test", "signature_id": "sig_missing"},
    )
    assert response.status_code == 401
