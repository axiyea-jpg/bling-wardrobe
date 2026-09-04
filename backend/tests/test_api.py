from fastapi.testclient import TestClient
import hashlib
import io
from PIL import Image

import pytest

from app.main import app
from app.settings import settings


client = TestClient(app)


def image_bytes(color=(240, 220, 210)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 96), color).save(stream, "PNG")
    return stream.getvalue()


def flatlay_bytes() -> bytes:
    image = Image.new("RGB", (720, 720), "white")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((55, 70, 300, 305), 24, fill=(180, 85, 110))
    draw.rounded_rectangle((410, 75, 655, 310), 24, fill=(70, 105, 160))
    draw.ellipse((95, 450, 270, 620), fill=(90, 65, 50))
    draw.ellipse((455, 455, 630, 625), fill=(65, 55, 105))
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


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
    result = upload_one("米白衬衫.png", image_bytes())
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
    first_raw = image_bytes((210, 180, 160))
    first = upload_one("同名外套.png", first_raw)
    first_id = first["result"]["garments"][0]["id"]
    assert client.post(f"/api/garments/{first_id}/approve").status_code == 200

    duplicate = client.post("/api/import/jobs", json={"files":[{
        "name":"另一个文件名.png", "content_type":"image/png", "size":22,
        "sha256":hashlib.sha256(first_raw).hexdigest(),
    }]}).json()
    assert duplicate["uploads"][0]["duplicate"] is True
    assert duplicate["uploads"][0]["garment_id"] == first_id

    second = upload_one("同名外套.png", image_bytes((160, 180, 220)))
    second_id = second["result"]["garments"][0]["id"]
    assert second_id != first_id


def test_user_store_isolates_identical_ids_between_users():
    from app.cloud_store import garment_store
    garment_store.put("user-a", "same-id", {"id":"same-id", "name":"A"})
    garment_store.put("user-b", "same-id", {"id":"same-id", "name":"B"})
    assert garment_store.get("user-a", "same-id")["name"] == "A"
    assert garment_store.get("user-b", "same-id")["name"] == "B"


def test_local_photo_endpoint_processes_real_images_and_exact_season_filter():
    response = client.post(
        "/api/import/photos",
        files=[("files", ("春夏蓝色直筒裤.png", image_bytes((100, 140, 210)), "image/png"))],
        data={"source": "album"},
    )
    assert response.status_code == 200
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "review"
    garment = job["result"]["garments"][0]
    assert garment["season"] == "春夏"
    assert garment["category"] == "裤子"
    assert garment["thumbnail_url"]
    assert client.post(f"/api/garments/{garment['id']}/approve").status_code == 200
    assert client.get("/api/garments?season=春夏").json()["total"] == 1
    assert client.get("/api/garments?season=春").json()["total"] == 0


def test_system_status_reports_real_local_capabilities():
    status = client.get("/api/system/status")
    assert status.status_code == 200
    body = status.json()
    assert body["storage"] == "sqlite+files"
    assert body["models"]["cutout"]["ready"] is True
    assert isinstance(body["models"]["ai_rebuild"]["ready"], bool)


def test_clean_product_is_basic_cutout_with_four_review_urls():
    result = upload_one("干净背景米白衬衫.png", image_bytes())
    garment = result["result"]["garments"][0]
    assert garment["input_type"] == "clean_product"
    assert garment["processing_mode"] == "basic_cutout"
    assert garment["ai_required"] is False
    assert garment["reconstruction_label"] == "真实基础抠图"
    assert garment["original_url"] and garment["cutout_url"] and garment["white_bg_url"]


def test_worn_photo_requires_ai_and_never_calls_basic_cutout_a_reconstruction():
    result = upload_one("真人穿着针织衫.png", image_bytes((205, 165, 150)))
    garment = result["result"]["garments"][0]
    assert garment["input_type"] == "worn"
    assert garment["ai_required"] is True
    assert garment["ai_status"] in {"unavailable", "ready", "failed"}
    if garment["ai_status"] != "ready":
        assert garment["display_variant"] == "white"
        assert garment["reconstruction_label"] == "真实基础抠图"
        assert garment["ai_url"] is None
        assert garment["original_url"]


def test_multi_flatlay_creates_independent_candidates_and_detection_boxes():
    result = upload_one("多件穿搭平铺图.png", flatlay_bytes())
    garments = result["result"]["garments"]
    assert len(garments) >= 2
    assert all(row["input_type"] == "multi_flatlay" for row in garments)
    assert len({row["id"] for row in garments}) == len(garments)
    assert len({row["original_url"] for row in garments}) == len(garments)
    assert all(row["source_image_url"] for row in garments)
    assert all(row["detection_bbox"] for row in garments)
    assert all(row["candidate_count"] == len(garments) for row in garments)
