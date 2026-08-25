InvalidOperation: 
Line |
   2 |  [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Literal ��
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot set property. Property setting is supported only on core types in this language mode.
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_reports_optional_services_without_faking_them():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["body_model_ready"], bool)
    assert isinstance(body["generation_ready"], bool)


def test_missing_body_weights_returns_actionable_503():
    response = client.post("/api/body-models", json={
        "height": 162, "weight": 52, "bust": 84,
        "waist": 66, "hip": 92, "shoulder": 38,
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "body_model_unavailable"

