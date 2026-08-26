from fastapi.testclient import TestClient
import hashlib

import pytest

from app.main import app
from app.settings import settings


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_data(tmp_path):
    previous = settings.data_dir
    settings.data_dir = tmp_path
    yield
    settings.data_dir = previous


def test_health_reports_optional_services_without_faking_them():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["body_model_ready"], bool)
    assert isinstance(body["generation_ready"], bool)


def test_body_endpoint_generates_a_real_glb_without_optional_weights():
    response = client.post("/api/body-models", json={
        "height": 162, "weight": 52, "bust": 84,
        "waist": 66, "hip": 92, "shoulder": 38,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["body_model_id"]
    assert result["glb_url"].endswith(".glb")
    glb = client.get(result["glb_url"])
    assert glb.status_code == 200
    assert glb.content[:4] == b"glTF"
    assert len(glb.content) > 20_000
    assert client.get(result["front_reference_url"]).status_code == 200


def upload_one(name: str, raw: bytes) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    created = client.post("/api/import/jobs", json={"files":[{
        "name":name, "content_type":"image/png", "size":len(raw), "sha256":digest,
    }]})
    assert created.status_code == 200
    job = created.json()
    upload = job["uploads"][0]
    if not upload.get("duplicate"):
        target = upload["upload_url"].replace("http://testserver", "")
        sent = client.put(target, content=raw, headers=upload["headers"])
        assert sent.status_code == 200
    completed = client.post(f"/api/import/jobs/{job['id']}/complete")
    assert completed.status_code == 200
    status = client.get(f"/api/jobs/{job['id']}")
    assert status.status_code == 200
    return status.json()


def test_cloud_style_import_uses_stable_ids_and_real_urls():
    result = upload_one("米白衬衫.png", b"unique-image-a")
    assert result["status"] == "review"
    garment = result["result"]["garments"][0]
    assert garment["id"]
    approved = client.post(f"/api/garments/{garment['id']}/approve")
    assert approved.status_code == 200
    row = approved.json()
    assert row["thumbnail_url"].startswith("/objects/users/local-owner/")
    assert "data:image" not in row["thumbnail_url"]
    listed = client.get("/api/garments?status=approved").json()["items"]
    assert [item["id"] for item in listed] == [garment["id"]]


def test_duplicate_content_is_not_reimported_but_same_name_different_content_is_allowed():
    first = upload_one("同名外套.png", b"first-physical-garment")
    first_id = first["result"]["garments"][0]["id"]
    assert client.post(f"/api/garments/{first_id}/approve").status_code == 200

    duplicate = client.post("/api/import/jobs", json={"files":[{
        "name":"另一个文件名.png", "content_type":"image/png", "size":22,
        "sha256":hashlib.sha256(b"first-physical-garment").hexdigest(),
    }]}).json()
    assert duplicate["uploads"][0]["duplicate"] is True
    assert duplicate["uploads"][0]["garment_id"] == first_id

    second = upload_one("同名外套.png", b"different-physical-garment")
    second_id = second["result"]["garments"][0]["id"]
    assert second_id != first_id


def test_user_store_isolates_identical_ids_between_users():
    from app.cloud_store import garment_store
    garment_store.put("user-a", "same-id", {"id":"same-id", "name":"A"})
    garment_store.put("user-b", "same-id", {"id":"same-id", "name":"B"})
    assert garment_store.get("user-a", "same-id")["name"] == "A"
    assert garment_store.get("user-b", "same-id")["name"] == "B"
