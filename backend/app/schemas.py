from typing import Literal
from pydantic import BaseModel, Field, field_validator


Category = Literal["上衣", "外套", "裤子", "裙子", "鞋", "包", "配饰", "头巾"]
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
    details: list[str] | None = None
    locked_fields: list[str] | None = None
    display_variant: Literal["original", "cutout", "white", "ai"] | None = None


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
    details: list[str] = []
    confidence: dict[str, float] = {}
    locked_fields: list[str] = []
    display_variant: str = "white"
    original_url: str
    source_image_url: str | None = None
    cutout_url: str | None = None
    white_bg_url: str | None = None
    ai_url: str | None = None
    thumbnail_url: str | None = None
    modeled_preview_url: str | None = None
    source_hash: str
    input_type: Literal["clean_product", "worn", "multi_flatlay", "complex_single"] = "clean_product"
    processing_mode: str = "basic_cutout"
    ai_required: bool = False
    ai_status: Literal["not_needed", "pending", "ready", "unavailable", "failed"] = "not_needed"
    ai_reason: str = ""
    reconstruction_label: str = "真实基础抠图"
    detection_bbox: list[float] | None = None
    candidate_index: int = 0
    candidate_count: int = 1
    source_position: int = 0
    status: Literal["processing", "review", "approved", "rejected"] = "processing"


class CropRequest(BaseModel):
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)
    rotation: float = Field(default=0, ge=-180, le=180)


class ProcessRequest(BaseModel):
    mode: Literal["cutout", "ai_generate"] = "cutout"


class PageCapture(BaseModel):
    url: str
    title: str = ""
    images: list[str] = []
    description: str = ""
    variants: list[str] = []


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
