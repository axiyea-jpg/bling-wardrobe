from __future__ import annotations

import hashlib
import ipaddress
import shutil
import socket
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import User, current_user
from .body_shape import body_service
from .cloud_store import body_store, garment_store, job_store, object_store, reference_store
from .local_pipeline import (
    CATEGORIES, SEASONS, analyze_input_image, capabilities, crop_image,
    extract_candidate, heuristic_labels, make_display_thumbnail, process_image,
)
from .local_models import analyze_garment as analyze_local_garment, rebuild_garment
from .openai_pipeline import analyze_and_cutout, generate_modeled_preview, generate_tryon
from .schemas import BodyMeasurements, BodyModelResult, CropRequest, Garment, GarmentPatch, ImportJobRequest, Job, PageCapture, ProcessRequest, TryOnRequest
from .settings import settings
from .task_queue import dispatch

app = FastAPI(title="Bling Wardrobe Local API", version="4.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in [settings.frontend_origin, "http://localhost:8000", "http://127.0.0.1:8000", settings.local_origin, "null"] if origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Bling-Token"],
)


def public_garment(row: dict) -> dict:
    result = {key: value for key, value in row.items() if not key.endswith("_object") and key not in {"user_id", "upload_token"}}
    result["original_url"] = object_store.signed_read_url(row.get("original_object", ""))
    result["source_image_url"] = object_store.signed_read_url(row.get("source_original_object", row.get("original_object", ""))) or None
    result["cutout_url"] = object_store.signed_read_url(row.get("cutout_object", "")) or None
    result["white_bg_url"] = object_store.signed_read_url(row.get("white_bg_object", "")) or None
    result["thumbnail_url"] = object_store.signed_read_url(row.get("thumbnail_object", "")) or None
    result["modeled_preview_url"] = object_store.signed_read_url(row.get("modeled_preview_object", "")) or None
    result["ai_url"] = object_store.signed_read_url(row.get("ai_object", "")) or None
    return result


def public_job(row: dict) -> dict:
    result = dict(row)
    job_result = result.get("result") or {}
    if job_result.get("garments"):
        result["result"] = dict(job_result, garments=[public_garment(g) for g in job_result["garments"]])
    return result


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True, "api_version": "4.2.0", "body_model_ready": body_service.available, "body_model_backend": body_service.backend_name,
        "generation_ready": bool(settings.openai_api_key), "cloud_storage_ready": object_store.cloud,
        "firebase_auth_required": bool(settings.firebase_project_id),
    }


@app.get("/api/system/status")
def system_status() -> dict:
    return {
        "ok": True,
        "mode": "local",
        "storage": "sqlite+files",
        "database": str((settings.data_dir / "bling-wardrobe.sqlite3").resolve()),
        "models": capabilities(),
        "body_model": {"ready": body_service.available, "backend": body_service.backend_name},
    }


@app.get("/objects/{path:path}")
def local_object(path: str, user: User = Depends(current_user)) -> FileResponse:
    if object_store.cloud:
        raise HTTPException(404)
    if not path.startswith(f"users/{user.uid}/"):
        raise HTTPException(403)
    target = object_store.local_path(path).resolve()
    root = (settings.data_dir / "objects").resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


@app.post("/api/body-models", response_model=BodyModelResult)
def create_body_model(body: BodyMeasurements, user: User = Depends(current_user)) -> BodyModelResult:
    try:
        return body_service.generate(body, user.uid)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            503,
            detail={"code": "body_model_unavailable", "message": str(exc)},
        ) from exc


@app.post("/api/import/jobs")
def create_import_job(payload: ImportJobRequest, user: User = Depends(current_user)) -> dict:
    job_id = uuid.uuid4().hex
    uploads, records = [], []
    existing = garment_store.list(user.uid)
    for manifest in payload.files:
        duplicates = [row for row in existing if (row.get("source_image_hash") or row.get("source_hash")) == manifest.sha256 and row.get("status") != "rejected"]
        if duplicates:
            records.extend({"duplicate_id": duplicate["id"], "manifest": manifest.model_dump()} for duplicate in duplicates)
            uploads.append({"duplicate": True, "garment_id": duplicates[0]["id"], "garment_ids": [row["id"] for row in duplicates], "upload_url": "", "method": "SKIP", "headers": {}})
            continue
        file_id = uuid.uuid4().hex + (Path(manifest.name).suffix.lower() or ".img")
        upload = object_store.upload_target(user.uid, job_id, file_id, manifest.content_type)
        uploads.append({key: value for key, value in upload.items() if key not in {"object_name", "upload_token"}})
        records.append({"manifest": manifest.model_dump(), "file_id": file_id, **upload})
    row = Job(id=job_id, kind="import", status="queued", progress=0).model_dump()
    row["uploads"] = records
    row["body_model_id"] = payload.body_model_id or ""
    job_store.put(user.uid, job_id, row)
    return {"id": job_id, "uploads": uploads}


@app.put("/api/import/jobs/{job_id}/files/{file_id}")
async def local_upload(job_id: str, file_id: str, request: Request, upload_token: str = Query("")) -> dict:
    if object_store.cloud:
        raise HTTPException(404)
    owner = None
    local_job = job_store.get("local-owner", job_id)
    if local_job and any(x.get("file_id") == file_id and x.get("upload_token") == upload_token for x in local_job.get("uploads", [])):
        owner = "local-owner"
    users_root = settings.data_dir / "users"
    for user_dir in users_root.glob("*") if users_root.exists() and not owner else []:
        row = job_store.get(user_dir.name, job_id)
        if row and any(x.get("file_id") == file_id and x.get("upload_token") == upload_token for x in row.get("uploads", [])):
            owner = user_dir.name
            break
    if not owner:
        raise HTTPException(403)
    job = job_store.get(owner, job_id)
    record = next(x for x in job["uploads"] if x.get("file_id") == file_id)
    raw = await request.body()
    if hashlib.sha256(raw).hexdigest() != record["manifest"]["sha256"]:
        raise HTTPException(400, detail={"code":"hash_mismatch", "message":"上传图片校验失败。"})
    object_store.write_local(record["object_name"], raw)
    return {"uploaded": True}


def process_import(uid: str, job_id: str) -> None:
    row = job_store.get(uid, job_id)
    if not row:
        return
    row.update(status="processing", progress=3)
    job_store.put(uid, job_id, row)
    created = []
    try:
        records = row.get("uploads", [])
        for position, record in enumerate(records):
            if record.get("duplicate_id"):
                duplicate = garment_store.get(uid, record["duplicate_id"])
                if duplicate:
                    created.append(duplicate)
                continue
            source = object_store.materialize(record["object_name"])
            if not source.exists():
                raise RuntimeError(f"图片尚未上传：{record['manifest']['name']}")
            inspection = analyze_input_image(source, record["manifest"]["name"])
            detections = inspection.get("detections") or [{"index": 0, "bbox": [0, 0, 1, 1], "confidence": .5}]
            ai_capability = capabilities()["ai_rebuild"]
            for candidate_position, detection in enumerate(detections):
                garment_id = uuid.uuid4().hex
                garment_dir = settings.data_dir / "garments" / garment_id
                bbox = detection["bbox"]
                candidate_source = source
                original_object = record["object_name"]
                if len(detections) > 1 or bbox != [0, 0, 1, 1]:
                    candidate_source = extract_candidate(source, bbox, garment_dir / "candidate-original.png")
                    original_object = object_store.upload_generated(uid, "candidate-originals", candidate_source, f"{garment_id}.png")
                outputs = process_image(candidate_source, garment_dir)
                generated = {}
                for field, folder in (("cutout", "cutouts"), ("white", "white-bg"), ("thumbnail", "thumbnails")):
                    if outputs.get(field):
                        generated[field] = object_store.upload_generated(uid, folder, outputs[field], f"{garment_id}{outputs[field].suffix}")
                ai_object, ai_status = "", "not_needed"
                display_variant = "white"
                reconstruction_label = "真实基础抠图"
                label_source = outputs.get("white") or outputs.get("cutout") or candidate_source
                if inspection["ai_required"]:
                    ai_status = "pending" if ai_capability["ready"] else "unavailable"
                    if ai_capability["ready"]:
                        try:
                            ai_output = rebuild_garment(candidate_source, garment_dir / "ai-flat-rebuild.png")
                            ai_object = object_store.upload_generated(uid, "ai-generated", ai_output, f"{garment_id}.png")
                            make_display_thumbnail(ai_output, garment_dir / "ai-thumb.webp")
                            generated["thumbnail"] = object_store.upload_generated(uid, "thumbnails", garment_dir / "ai-thumb.webp", f"{garment_id}.webp")
                            ai_status, display_variant, reconstruction_label, label_source = "ready", "ai", "AI 平铺重建", ai_output
                        except Exception:
                            ai_status = "failed"
                analyzed = analyze_local_garment(label_source, record["manifest"]["name"])
                candidate_hash = hashlib.sha256((record["manifest"]["sha256"] + ":" + str(candidate_position) + ":" + str(bbox)).encode()).hexdigest()
                garment = {
                    "id": garment_id, "name": analyzed.pop("name", Path(record["manifest"]["name"]).stem),
                    "category": analyzed.pop("category", "上衣"), "season": analyzed.pop("season", "四季"),
                    "color": analyzed.pop("color", "待识别"), "material": analyzed.pop("material", "待识别"),
                    "style": analyzed.pop("style", "待识别"), "fit": analyzed.pop("fit", "待识别"),
                    "tags": analyzed.pop("tags", []), "details": analyzed.pop("details", []),
                    "confidence": analyzed.pop("confidence", {}), "locked_fields": [], "display_variant": display_variant, "status": "review",
                    "source_hash": candidate_hash, "source_image_hash": record["manifest"]["sha256"],
                    "original_object": original_object, "source_original_object": record["object_name"],
                    "cutout_object": generated.get("cutout", ""), "white_bg_object": generated.get("white", ""),
                    "thumbnail_object": generated.get("thumbnail", ""), "ai_object": ai_object,
                    "modeled_preview_object": "", "input_type": inspection["input_type"],
                    "processing_mode": "ai_flat_rebuild" if ai_status == "ready" else "basic_cutout",
                    "ai_required": inspection["ai_required"], "ai_status": ai_status,
                    "ai_reason": ai_capability.get("reason", "") if ai_status == "unavailable" else "",
                    "reconstruction_label": reconstruction_label, "detection_bbox": bbox,
                    "candidate_index": candidate_position, "candidate_count": len(detections), "source_position": position, **analyzed,
                }
                garment_store.put(uid, garment_id, garment)
                created.append(garment)
            row["progress"] = 5 + int((position + 1) / max(1, len(records)) * 90)
            job_store.put(uid, job_id, row)
        row.update(status="review", progress=100, result={"garments": created})
    except Exception as exc:
        row.update(status="failed", error={"code":"import_failed", "message":str(exc)})
    job_store.put(uid, job_id, row)


@app.post("/api/import/jobs/{job_id}/complete")
def complete_import(job_id: str, background: BackgroundTasks, user: User = Depends(current_user)) -> Job:
    row = job_store.get(user.uid, job_id)
    if not row:
        raise HTTPException(404)
    if not dispatch("/internal/import/process", {"uid":user.uid, "job_id":job_id}):
        background.add_task(process_import, user.uid, job_id)
    return Job.model_validate(row)


@app.post("/api/import/photos")
async def import_photos(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    source: str = Form("album"),
    body_model_id: str = Form(""),
    user: User = Depends(current_user),
) -> dict:
    if not files:
        raise HTTPException(400, detail={"code": "no_files", "message": "请选择衣物照片。"})
    job_id = uuid.uuid4().hex
    records: list[dict] = []
    existing = garment_store.list(user.uid)
    for upload in files:
        raw = await upload.read()
        if not raw:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        duplicates = [row for row in existing if (row.get("source_image_hash") or row.get("source_hash")) == digest and row.get("status") != "rejected"]
        if duplicates:
            records.extend({"duplicate_id": duplicate["id"], "manifest": {"name": upload.filename or "photo.jpg", "sha256": digest}} for duplicate in duplicates)
            continue
        suffix = Path(upload.filename or "photo.jpg").suffix.lower() or ".jpg"
        file_id = uuid.uuid4().hex + suffix
        object_name = f"users/{user.uid}/imports/{job_id}/originals/{file_id}"
        object_store.upload_bytes(object_name, raw, upload.content_type or "image/jpeg")
        records.append({"manifest": {"name": upload.filename or file_id, "content_type": upload.content_type or "image/jpeg", "size": len(raw), "sha256": digest}, "file_id": file_id, "object_name": object_name})
    if not records:
        raise HTTPException(400, detail={"code": "empty_upload", "message": "没有可处理的照片。"})
    row = Job(id=job_id, kind="import", status="queued", progress=0).model_dump()
    row.update(uploads=records, body_model_id=body_model_id, source=source)
    job_store.put(user.uid, job_id, row)
    background.add_task(process_import, user.uid, job_id)
    return {"id": job_id, "status": "queued", "count": len(records)}


def _safe_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, detail={"code": "invalid_url", "message": "请输入有效的商品链接。"})
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback or ipaddress.ip_address(address).is_link_local for address in addresses):
            raise HTTPException(422, detail={"code": "private_url", "message": "链接不能指向本机或局域网地址。"})
    except socket.gaierror as exc:
        raise HTTPException(422, detail={"code": "unreachable_url", "message": "无法解析商品网站地址。"}) from exc
    return value


@app.post("/api/import/url")
async def import_url(payload: dict, user: User = Depends(current_user)) -> dict:
    url = _safe_public_url(str(payload.get("url", "")))
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12, headers={"User-Agent": "BlingWardrobeLocal/1.0"}) as client:
            response = await client.get(url)
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(422, detail={"code": "page_blocked", "message": "商品页无法直接读取，请在已登录商品页使用布灵网页助手。"}) from exc
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        return {"status": "candidate", "candidate": {"url": url, "title": Path(urlparse(url).path).stem or "商品图片", "images": [url], "description": "", "variants": []}}
    text = response.text[:2_000_000]
    import re
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    images = re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', text, re.I)
    if not images:
        raise HTTPException(422, detail={"code": "image_missing", "message": "商品页没有可读取的主图，请使用网页助手或从相册上传。"})
    return {"status": "candidate", "candidate": {"url": url, "title": (title.group(1).strip() if title else "商品单品"), "images": images[:8], "description": "", "variants": []}}


@app.post("/api/import/page-capture")
def import_page_capture(payload: PageCapture, user: User = Depends(current_user)) -> dict:
    _safe_public_url(payload.url)
    safe_images = [_safe_public_url(url) for url in payload.images[:12]]
    return {"status": "candidate", "candidate": {**payload.model_dump(), "images": safe_images}, "source": "browser-helper"}


def verify_task_secret(value: str) -> None:
    if not settings.cloud_tasks_secret or value != settings.cloud_tasks_secret:
        raise HTTPException(403)


@app.post("/internal/import/process")
def internal_import(payload: dict, x_task_secret: str = Header("")) -> dict:
    verify_task_secret(x_task_secret)
    process_import(str(payload["uid"]), str(payload["job_id"]))
    return {"processed": True}


@app.get("/api/garments")
def list_garments(status: str = "approved", category: str = "", season: str = "", page: int = Query(1, ge=1), page_size: int = Query(0, ge=0, le=500), limit: int = Query(50, ge=1, le=500), cursor: str = "", user: User = Depends(current_user)) -> dict:
    rows = sorted(garment_store.list(user.uid), key=lambda row: row.get("id", ""))
    if status:
        rows = [row for row in rows if row.get("status") == status]
    if cursor:
        rows = [row for row in rows if row.get("id", "") > cursor]
    if category:
        rows = [row for row in rows if row.get("category") == category]
    if season:
        rows = [row for row in rows if row.get("season") == season]
    total = len(rows)
    size = page_size or limit
    selected = rows[(page - 1) * size:page * size]
    return {"items": [public_garment(row) for row in selected], "total": total, "page": page, "page_size": size, "next_cursor": selected[-1]["id"] if page * size < total and selected else None}


@app.patch("/api/garments/{garment_id}", response_model=Garment)
def update_garment(garment_id: str, patch: GarmentPatch, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    changes = patch.model_dump(exclude_none=True)
    if changes.get("category") and changes["category"] not in CATEGORIES:
        raise HTTPException(422, detail={"code": "invalid_category", "message": "请选择现有衣橱分类。"})
    if changes.get("season") and changes["season"] not in SEASONS:
        raise HTTPException(422, detail={"code": "invalid_season", "message": "季节标签无效。"})
    selected_variant = changes.get("display_variant")
    if selected_variant:
        object_field = {"original": "original_object", "cutout": "cutout_object", "white": "white_bg_object", "ai": "ai_object"}[selected_variant]
        if not row.get(object_field):
            raise HTTPException(409, detail={"code": "variant_unavailable", "message": "该图片版本尚未生成。"})
        selected = object_store.materialize(row[object_field])
        thumb = make_display_thumbnail(selected, settings.data_dir / "garments" / garment_id / "selected-thumb.webp")
        old = row.get("thumbnail_object", "")
        row["thumbnail_object"] = object_store.upload_generated(user.uid, "thumbnails", thumb, f"{garment_id}.webp")
        if old and old != row["thumbnail_object"]:
            object_store.delete(old)
        labels = analyze_local_garment(selected, row.get("name") or "单品")
        for key, value in labels.items():
            if key not in set(row.get("locked_fields", [])):
                row[key] = value
        row["reconstruction_label"] = "AI 平铺重建" if selected_variant == "ai" else "真实基础抠图"
    locked = set(row.get("locked_fields", []))
    locked.update(key for key in changes if key not in {"locked_fields", "display_variant"})
    row.update(changes)
    row["locked_fields"] = sorted(set(changes.get("locked_fields", [])) | locked)
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


def _replace_processed_objects(uid: str, garment_id: str, row: dict, outputs: dict[str, Path]) -> dict:
    for field, object_field, folder in (("cutout", "cutout_object", "cutouts"), ("white", "white_bg_object", "white-bg"), ("thumbnail", "thumbnail_object", "thumbnails")):
        if outputs.get(field):
            old = row.get(object_field, "")
            row[object_field] = object_store.upload_generated(uid, folder, outputs[field], f"{garment_id}{outputs[field].suffix}")
            if old and old != row[object_field]:
                object_store.delete(old)
    row["image_version"] = int(row.get("image_version", 0)) + 1
    return row


@app.post("/api/garments/{garment_id}/process", response_model=Garment)
def process_garment(garment_id: str, payload: ProcessRequest, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    if payload.mode == "ai_generate":
        status = capabilities()["ai_rebuild"]
        if not status["ready"]:
            raise HTTPException(409, detail={"code": "ai_unavailable", "message": status["reason"]})
        source = object_store.materialize(row["original_object"])
        ai_output = settings.data_dir / "garments" / garment_id / "ai-generated.png"
        try:
            rebuild_garment(source, ai_output)
        except Exception as exc:
            raise HTTPException(500, detail={"code": "ai_generation_failed", "message": str(exc)}) from exc
        row["ai_object"] = object_store.upload_generated(user.uid, "ai-generated", ai_output, f"{garment_id}.png")
        thumb = make_display_thumbnail(ai_output, settings.data_dir / "garments" / garment_id / "ai-thumb.webp")
        row["thumbnail_object"] = object_store.upload_generated(user.uid, "thumbnails", thumb, f"{garment_id}.webp")
        row["display_variant"] = "ai"
        row["ai_generated"] = True
        row["ai_status"] = "ready"
        row["processing_mode"] = "ai_flat_rebuild"
        row["reconstruction_label"] = "AI 平铺重建"
        labels = analyze_local_garment(ai_output, row.get("name") or "单品")
        for key, value in labels.items():
            if key not in set(row.get("locked_fields", [])):
                row[key] = value
        garment_store.put(user.uid, garment_id, row)
        return Garment.model_validate(public_garment(row))
    source = object_store.materialize(row["original_object"])
    outputs = process_image(source, settings.data_dir / "garments" / garment_id)
    _replace_processed_objects(user.uid, garment_id, row, outputs)
    row["status"] = "review"
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.post("/api/garments/{garment_id}/crop", response_model=Garment)
def crop_garment(garment_id: str, payload: CropRequest, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    source = object_store.materialize(row["original_object"])
    outputs = crop_image(source, settings.data_dir / "garments" / garment_id, payload.model_dump())
    _replace_processed_objects(user.uid, garment_id, row, outputs)
    row["crop"] = payload.model_dump()
    row["status"] = "review"
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.post("/api/garments/{garment_id}/scan", response_model=Garment)
async def scan_garment(
    garment_id: str,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> Garment:
    """Re-run cutout on the scanner editor's rotated/positioned flat image.

    The original upload remains untouched, so the user can always reopen the
    scanner and make another non-destructive adjustment.
    """
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, detail={"code": "invalid_image", "message": "请选择图片文件"})
    raw = await file.read()
    if not raw:
        raise HTTPException(400, detail={"code": "empty_image", "message": "扫描图片为空"})
    output_dir = settings.data_dir / "garments" / garment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / "scanner-source.png"
    temporary.write_bytes(raw)
    try:
        outputs = process_image(temporary, output_dir)
    finally:
        temporary.unlink(missing_ok=True)
    _replace_processed_objects(user.uid, garment_id, row, outputs)
    row["status"] = "review"
    row["processing_mode"] = "scanner_cutout"
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.post("/api/garments/{garment_id}/reanalyze", response_model=Garment)
def reanalyze_garment(garment_id: str, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    field = {"original": "original_object", "cutout": "cutout_object", "white": "white_bg_object", "ai": "ai_object"}.get(row.get("display_variant", "white"), "white_bg_object")
    source = object_store.materialize(row.get(field) or row["original_object"])
    labels = analyze_local_garment(source, row.get("name") or Path(row.get("original_object", "photo.jpg")).name)
    locked = set(row.get("locked_fields", []))
    for key, value in labels.items():
        if key not in locked:
            row[key] = value
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.post("/api/garments/{garment_id}/approve", response_model=Garment)
def approve_garment(garment_id: str, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    if not row.get("thumbnail_object"):
        raise HTTPException(409, detail={"code": "image_not_ready", "message": "图片尚未成功处理，请补图或重新抠图后再确认。"})
    if settings.openai_api_key and settings.default_model_reference.exists() and not row.get("modeled_preview_object"):
        cutout = object_store.materialize(row["cutout_object"])
        output = settings.data_dir / "modeled" / user.uid / f"{garment_id}.png"
        generate_modeled_preview(settings.default_model_reference, cutout, output)
        row["modeled_preview_object"] = object_store.upload_generated(user.uid, "modeled", output, f"{garment_id}.png")
    row["status"] = "approved"
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.delete("/api/garments/{garment_id}")
def delete_garment(garment_id: str, user: User = Depends(current_user)) -> dict:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        return {"deleted": False}
    for key in ("original_object", "cutout_object", "white_bg_object", "thumbnail_object", "modeled_preview_object", "ai_object"):
        object_store.delete(row.get(key, ""))
    shutil.rmtree(settings.data_dir / "garments" / garment_id, ignore_errors=True)
    garment_store.delete(user.uid, garment_id)
    return {"deleted": True}


def process_tryon(uid: str, job_id: str, payload: TryOnRequest) -> None:
    row = job_store.get(uid, job_id) or Job(id=job_id, kind="tryon", status="processing", progress=10).model_dump()
    row.update(status="processing", progress=20)
    job_store.put(uid, job_id, row)
    try:
        row.update(result=generate_tryon(uid, payload), status="ready", progress=100)
    except HTTPException as exc:
        row.update(status="failed", error=exc.detail if isinstance(exc.detail, dict) else {"message":str(exc.detail)})
    except Exception as exc:
        row.update(status="failed", error={"code":"generation_failed", "message":str(exc)})
    job_store.put(uid, job_id, row)


@app.post("/api/tryon/jobs")
def tryon_job(payload: TryOnRequest, background: BackgroundTasks, user: User = Depends(current_user)) -> Job:
    job_id = uuid.uuid4().hex
    row = Job(id=job_id, kind="tryon", status="queued").model_dump()
    job_store.put(user.uid, job_id, row)
    if not dispatch("/internal/tryon/process", {"uid":user.uid, "job_id":job_id, "payload":payload.model_dump()}):
        background.add_task(process_tryon, user.uid, job_id, payload)
    return Job.model_validate(row)


@app.post("/internal/tryon/process")
def internal_tryon(payload: dict, x_task_secret: str = Header("")) -> dict:
    verify_task_secret(x_task_secret)
    process_tryon(str(payload["uid"]), str(payload["job_id"]), TryOnRequest.model_validate(payload["payload"]))
    return {"processed": True}


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, user: User = Depends(current_user)) -> Job:
    row = job_store.get(user.uid, job_id)
    if not row:
        raise HTTPException(404)
    return Job.model_validate(public_job(row))


@app.post("/api/reference-photo")
async def upload_reference(request: Request, user: User = Depends(current_user)) -> dict:
    raw = await request.body()
    if not raw:
        raise HTTPException(400)
    ref_id = uuid.uuid4().hex
    object_name = f"users/{user.uid}/references/{ref_id}.png"
    object_store.upload_bytes(object_name, raw, request.headers.get("content-type", "image/png"))
    reference_store.put(user.uid, ref_id, {"id":ref_id, "object_name":object_name})
    return {"reference_photo_id":ref_id}


@app.delete("/api/reference-photo/{reference_id}")
def delete_reference(reference_id: str, user: User = Depends(current_user)) -> dict:
    row = reference_store.get(user.uid, reference_id)
    if row:
        object_store.delete(row.get("object_name", ""))
        reference_store.delete(user.uid, reference_id)
    return {"deleted": True}


# The local edition serves the existing product UI from the same trusted origin.
frontend_dir = Path(__file__).resolve().parents[2]
if (frontend_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
