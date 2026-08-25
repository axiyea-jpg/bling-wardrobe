from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .body_shape import body_service
from .files import public_url, save_upload
from .openai_pipeline import analyze_and_cutout, generate_tryon
from .schemas import BodyMeasurements, BodyModelResult, Garment, GarmentPatch, Job, TryOnRequest
from .settings import settings
from .store import garments, jobs, references


app = FastAPI(title="Bling Wardrobe Generation API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Bling-Token"],
)


def owner_auth(x_bling_token: Annotated[str | None, Header()] = None) -> None:
    if settings.owner_token and x_bling_token != settings.owner_token:
        raise HTTPException(401, detail={"code": "unauthorized", "message": "生成服务连接码无效。"})


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "body_model_ready": body_service.available, "generation_ready": bool(settings.openai_api_key)}


@app.get("/files/{path:path}", dependencies=[Depends(owner_auth)])
def files(path: str) -> FileResponse:
    target = (settings.data_dir / path).resolve()
    if settings.data_dir.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


@app.post("/api/body-models", response_model=BodyModelResult, dependencies=[Depends(owner_auth)])
def create_body_model(body: BodyMeasurements) -> BodyModelResult:
    return body_service.generate(body)


async def _make_import_job(job_id: str, uploads: list[UploadFile]) -> None:
    job = Job(id=job_id, kind="import", status="processing", progress=5)
    jobs.put(job_id, job.model_dump())
    created = []
    try:
        for position, upload in enumerate(uploads):
            path, digest = await save_upload(upload, "originals")
            garment_id = uuid.uuid4().hex
            analyzed = analyze_and_cutout(path, digest) if settings.openai_api_key else {}
            row = Garment(
                id=garment_id, name=Path(upload.filename or f"单品{position+1}").stem,
                category="上衣", season="四季", color="待识别", material="待识别",
                style="待识别", fit="待识别", tags=["待确认"], original_url=public_url(path),
                source_hash=digest, status="review",
            ).model_dump()
            row["original_path"] = str(path)
            row.update(analyzed)
            garments.put(garment_id, row)
            created.append(row)
            job.progress = int((position + 1) / max(1, len(uploads)) * 90)
            jobs.put(job_id, job.model_dump())
        job.status, job.progress, job.result = "review", 100, {"garments": created}
    except Exception as exc:
        job.status, job.error = "failed", {"code": "import_failed", "message": str(exc)}
    jobs.put(job_id, job.model_dump())


@app.post("/api/import/jobs", dependencies=[Depends(owner_auth)])
async def import_job(background: BackgroundTasks, files: list[UploadFile] = File(...)) -> Job:
    job_id = uuid.uuid4().hex
    # UploadFile streams must be consumed before request cleanup, so v1 processes in-request.
    await _make_import_job(job_id, files)
    return Job.model_validate(jobs.get(job_id))


@app.patch("/api/garments/{garment_id}", response_model=Garment, dependencies=[Depends(owner_auth)])
def update_garment(garment_id: str, patch: GarmentPatch) -> Garment:
    row = garments.get(garment_id)
    if not row:
        raise HTTPException(404)
    row.update(patch.model_dump(exclude_none=True))
    garments.put(garment_id, row)
    return Garment.model_validate(row)


@app.post("/api/garments/{garment_id}/approve", response_model=Garment, dependencies=[Depends(owner_auth)])
def approve_garment(garment_id: str) -> Garment:
    row = garments.get(garment_id)
    if not row:
        raise HTTPException(404)
    # Until AI cutout finishes, approving keeps the unique original instead of any sprite fallback.
    row["cutout_path"] = row.get("cutout_path") or row["original_path"]
    row["cutout_url"] = row.get("cutout_url") or row["original_url"]
    row["thumbnail_url"] = row.get("thumbnail_url") or row["cutout_url"]
    row["status"] = "approved"
    garments.put(garment_id, row)
    return Garment.model_validate(row)


def _tryon(job_id: str, request: TryOnRequest) -> None:
    job = Job(id=job_id, kind="tryon", status="processing", progress=20)
    jobs.put(job_id, job.model_dump())
    try:
        job.result = generate_tryon(request)
        job.status, job.progress = "ready", 100
    except HTTPException as exc:
        job.status, job.error = "failed", exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    except Exception as exc:
        job.status, job.error = "failed", {"code": "generation_failed", "message": str(exc)}
    jobs.put(job_id, job.model_dump())


@app.post("/api/tryon/jobs", dependencies=[Depends(owner_auth)])
def tryon_job(request: TryOnRequest, background: BackgroundTasks) -> Job:
    job_id = uuid.uuid4().hex
    job = Job(id=job_id, kind="tryon", status="queued")
    jobs.put(job_id, job.model_dump())
    background.add_task(_tryon, job_id, request)
    return job


@app.get("/api/jobs/{job_id}", response_model=Job, dependencies=[Depends(owner_auth)])
def get_job(job_id: str) -> Job:
    row = jobs.get(job_id)
    if not row:
        raise HTTPException(404)
    return Job.model_validate(row)


@app.post("/api/reference-photo", dependencies=[Depends(owner_auth)])
async def upload_reference(file: UploadFile = File(...)) -> dict:
    path, digest = await save_upload(file, "references")
    ref_id = uuid.uuid4().hex
    row = {"id": ref_id, "path": str(path), "source_hash": digest}
    references.put(ref_id, row)
    return {"reference_photo_id": ref_id}


@app.delete("/api/reference-photo/{reference_id}", dependencies=[Depends(owner_auth)])
def delete_reference(reference_id: str) -> dict:
    row = references.get(reference_id)
    if row:
        Path(row["path"]).unlink(missing_ok=True)
        references.delete(reference_id)
    return {"deleted": True}
