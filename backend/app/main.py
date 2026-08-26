from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import User, current_user
from .body_shape import body_service
from .cloud_store import garment_store, job_store, object_store, reference_store
from .openai_pipeline import analyze_and_cutout, generate_modeled_preview, generate_tryon
from .schemas import BodyMeasurements, BodyModelResult, Garment, GarmentPatch, ImportJobRequest, Job, TryOnRequest
from .settings import settings
from .store import body_models
from .task_queue import dispatch

app = FastAPI(title="Bling Wardrobe Cloud API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def public_garment(row: dict) -> dict:
    result = {key: value for key, value in row.items() if not key.endswith("_object") and key not in {"user_id", "upload_token"}}
    result["original_url"] = object_store.signed_read_url(row.get("original_object", ""))
    result["cutout_url"] = object_store.signed_read_url(row.get("cutout_object", "")) or None
    result["thumbnail_url"] = object_store.signed_read_url(row.get("thumbnail_object", "") or row.get("cutout_object", "")) or None
    result["modeled_preview_url"] = object_store.signed_read_url(row.get("modeled_preview_object", "")) or None
    return result


def public_job(row: dict) -> dict:
    result = dict(row)
    if result.get("result", {}).get("garments"):
        result["result"] = dict(result["result"], garments=[public_garment(g) for g in result["result"]["garments"]])
    return result


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True, "body_model_ready": body_service.available,
        "generation_ready": bool(settings.openai_api_key), "cloud_storage_ready": object_store.cloud,
        "firebase_auth_required": bool(settings.firebase_project_id),
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
    return body_service.generate(body)


@app.post("/api/import/jobs")
def create_import_job(payload: ImportJobRequest, user: User = Depends(current_user)) -> dict:
    job_id = uuid.uuid4().hex
    uploads, records = [], []
    existing = garment_store.list(user.uid)
    for manifest in payload.files:
        duplicate = next((row for row in existing if row.get("source_hash") == manifest.sha256 and row.get("status") != "rejected"), None)
        if duplicate:
            records.append({"duplicate_id": duplicate["id"], "manifest": manifest.model_dump()})
            uploads.append({"duplicate": True, "garment_id": duplicate["id"], "upload_url": "", "method": "SKIP", "headers": {}})
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
    users_root = settings.data_dir / "users"
    for user_dir in users_root.glob("*") if users_root.exists() else []:
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
            garment_id = uuid.uuid4().hex
            analyzed = analyze_and_cutout(source, record["manifest"]["sha256"]) if settings.openai_api_key else {}
            cutout_object = ""
            if analyzed.get("cutout_path"):
                cutout_path = Path(analyzed.pop("cutout_path"))
                cutout_object = object_store.upload_generated(uid, "cutouts", cutout_path, f"{record['manifest']['sha256']}.png")
            garment = {
                "id": garment_id, "name": analyzed.pop("name", Path(record["manifest"]["name"]).stem),
                "category": analyzed.pop("category", "上衣"), "season": analyzed.pop("season", "四季"),
                "color": analyzed.pop("color", "待识别"), "material": analyzed.pop("material", "待识别"),
                "style": analyzed.pop("style", "待识别"), "fit": analyzed.pop("fit", "待识别"),
                "tags": analyzed.pop("tags", ["待确认"]), "status": "review",
                "source_hash": record["manifest"]["sha256"], "original_object": record["object_name"],
                "cutout_object": cutout_object, "thumbnail_object": cutout_object,
                "modeled_preview_object": "", **analyzed,
            }
            model_reference = settings.default_model_reference
            selected_model = body_models.get(row.get("body_model_id") or "")
            if selected_model and selected_model.get("front_reference_url"):
                candidate = Path(selected_model["front_reference_url"])
                if candidate.exists():
                    model_reference = candidate
            if settings.openai_api_key and model_reference.exists() and cutout_object:
                modeled_output = settings.data_dir / "modeled" / uid / f"{garment_id}.png"
                generate_modeled_preview(model_reference, object_store.materialize(cutout_object), modeled_output)
                garment["modeled_preview_object"] = object_store.upload_generated(
                    uid, "modeled", modeled_output, f"{garment_id}.png"
                )
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


def verify_task_secret(value: str) -> None:
    if not settings.cloud_tasks_secret or value != settings.cloud_tasks_secret:
        raise HTTPException(403)


@app.post("/internal/import/process")
def internal_import(payload: dict, x_task_secret: str = Header("")) -> dict:
    verify_task_secret(x_task_secret)
    process_import(str(payload["uid"]), str(payload["job_id"]))
    return {"processed": True}


@app.get("/api/garments")
def list_garments(status: str = "approved", limit: int = Query(50, ge=1, le=500), cursor: str = "", user: User = Depends(current_user)) -> dict:
    rows = sorted(garment_store.list(user.uid), key=lambda row: row.get("id", ""))
    if status:
        rows = [row for row in rows if row.get("status") == status]
    if cursor:
        rows = [row for row in rows if row.get("id", "") > cursor]
    page = rows[:limit]
    return {"items": [public_garment(row) for row in page], "next_cursor": page[-1]["id"] if len(rows) > limit and page else None}


@app.patch("/api/garments/{garment_id}", response_model=Garment)
def update_garment(garment_id: str, patch: GarmentPatch, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    row.update(patch.model_dump(exclude_none=True))
    garment_store.put(user.uid, garment_id, row)
    return Garment.model_validate(public_garment(row))


@app.post("/api/garments/{garment_id}/approve", response_model=Garment)
def approve_garment(garment_id: str, user: User = Depends(current_user)) -> Garment:
    row = garment_store.get(user.uid, garment_id)
    if not row:
        raise HTTPException(404)
    if not row.get("cutout_object"):
        row["cutout_object"] = row["original_object"]
        row["thumbnail_object"] = row["original_object"]
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
    for key in ("original_object", "cutout_object", "thumbnail_object", "modeled_preview_object"):
        object_store.delete(row.get(key, ""))
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
