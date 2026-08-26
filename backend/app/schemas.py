from typing import Literal
from pydantic import BaseModel, Field, field_validator


Category = Literal["上衣", "外套", "裤子", "裙子", "连衣裙", "鞋", "包", "配饰", "头巾"]
JobStatus = Literal["queued", "processing", "review", "ready", "failed"]


class BodyMeasurements(BaseModel):
    height: float = Field(ge=140, le=205)
    weight: float = Field(ge=35, le=180)
    bust: float = Field(ge=65, le=155)
    waist: float = Field(ge=45, le=150)
    hip: float = Field(ge=65, le=165)
    shoulder: float = Field(ge=28, le=60)
    neck: float | None = Field(default=None, ge=25, le=60)
    natural_waist: float | None = Field(default=None, ge=45, le=150)
    thigh: float | None = Field(default=None, ge=30, le=100)
    knee: float | None = Field(default=None, ge=25, le=75)
    wrist: float | None = Field(default=None, ge=10, le=35)
    upper_arm: float | None = Field(default=None, ge=18, le=70)
    leg_length: float | None = Field(default=None, ge=60, le=125)


class BodyModelResult(BaseModel):
    body_model_id: str
    completed_measurements: dict[str, float]
    glb_url: str
    front_reference_url: str
    three_quarter_reference_url: str
    warnings: list[str] = []


class GarmentPatch(BaseModel):
    name: str | None = None
    category: Category | None = None
    season: str | None = None
    color: str | None = None
    material: str | None = None
    style: str | None = None
    fit: str | None = None
    tags: list[str] | None = None


class Garment(BaseModel):
    id: str
    name: str
    category: Category
    season: str
    color: str
    material: str
    style: str
    fit: str
    tags: list[str] = []
    original_url: str
    cutout_url: str | None = None
    thumbnail_url: str | None = None
    modeled_preview_url: str | None = None
    source_hash: str
    status: Literal["processing", "review", "approved", "rejected"] = "processing"


class TryOnRequest(BaseModel):
    model_mode: Literal["digital", "real"] = "digital"
    body_model_id: str | None = None
    reference_photo_id: str | None = None
    garment_ids: list[str] = Field(min_length=1, max_length=8)
    scene: str = "日常通勤"
    quality: Literal["draft", "final"] = "draft"

    @field_validator("garment_ids")
    @classmethod
    def unique_garments(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("garment_ids must be unique")
        return value


class Job(BaseModel):
    id: str
    kind: Literal["import", "tryon"]
    status: JobStatus
    progress: int = 0
    result: dict | None = None
    error: dict | None = None


class UploadManifest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(pattern=r"^image/")
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ImportJobRequest(BaseModel):
    files: list[UploadManifest] = Field(min_length=1)
    body_model_id: str | None = None
