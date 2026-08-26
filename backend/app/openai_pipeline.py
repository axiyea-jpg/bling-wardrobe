from __future__ import annotations

import base64
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from openai import OpenAI
from PIL import Image

from .schemas import TryOnRequest
from .settings import settings
from .store import body_models
from .cloud_store import garment_store, object_store, reference_store


def client() -> OpenAI:
    if not settings.openai_api_key:
        raise HTTPException(503, detail={"code": "generation_not_configured", "message": "生成服务尚未配置 OpenAI API 密钥。"})
    return OpenAI(api_key=settings.openai_api_key)


def tryon_cache_key(request: TryOnRequest, model_ref: str, garment_rows: list[dict]) -> str:
    value = json.dumps({
        "model": settings.image_model,
        "prompt": "bling-tryon-v2",
        "reference": model_ref,
        "garments": [(x["id"], x.get("source_hash")) for x in garment_rows],
        "scene": request.scene,
        "quality": request.quality,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def _json_from_text(value: str) -> dict:
    value = value.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(value)


def analyze_and_cutout(source: Path, digest: str) -> dict:
    """Evidence-bound garment extraction based on tandpfun/wardrobe's workflow."""
    raw = source.read_bytes()
    mime = "image/png" if source.suffix.lower() == ".png" else "image/jpeg"
    data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    response = client().responses.create(
        model=settings.vision_model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": (
                "Analyze the main garment only. Return one JSON object with keys name, category, season, color, material, "
                "style, fit, tags. category must be one of 上衣,外套,裤子,裙子,连衣裙,鞋,包,配饰,头巾. "
                "Use one dominant color, distinguish denim/linen/cotton/knit/leather/chiffon, and distinguish straight, "
                "wide-leg, flare, fitted, waist-shaped, A-line, ruffled and oversized silhouettes. Use concise Chinese."
            )},
            {"type": "input_image", "image_url": data_url},
        ]}],
    )
    meta = _json_from_text(response.output_text)
    allowed = {"上衣", "外套", "裤子", "裙子", "连衣裙", "鞋", "包", "配饰", "头巾"}
    if meta.get("category") not in allowed:
        meta["category"] = "上衣"
    meta["tags"] = list(dict.fromkeys(meta.get("tags") or []))[:8]

    with source.open("rb") as image:
        edited = client().images.edit(
            model=settings.image_model,
            image=[image],
            prompt=(
                "Extract exactly the main garment from this source. Reconstruct only parts directly evidenced by the photo. "
                "Return one clean front-facing catalog cutout, centered and fully visible, with transparent background. "
                "Preserve exact color, fabric texture, silhouette, seams, neckline, sleeves and decorations. No person, hanger, "
                "text, watermark, shadow, border, duplicate item or invented design."
            ),
            size="1024x1024",
            quality="medium",
            output_format="png",
            background="transparent",
        )
    cutout_dir = settings.data_dir / "cutouts"
    cutout_dir.mkdir(parents=True, exist_ok=True)
    cutout = cutout_dir / f"{digest}.png"
    cutout.write_bytes(base64.b64decode(edited.data[0].b64_json))
    # Verify the artifact is a readable RGBA PNG before presenting it for review.
    with Image.open(cutout) as check:
        check.verify()
    return {**meta, "cutout_path": str(cutout)}


def generate_modeled_preview(model_path: Path, garment_path: Path, output: Path) -> Path:
    """Generate the import-time modeled preview used for instant single-item try-on."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with model_path.open("rb") as model, garment_path.open("rb") as garment:
        result = client().images.edit(
            model=settings.image_model,
            image=[model, garment],
            prompt=(
                "Create a polished full-body studio fashion photograph of the exact person in Image 1 wearing the exact "
                "garment in Image 2. Preserve identity, body proportions, garment color, material, construction, silhouette "
                "and details. Use only plain neutral supporting basics. No collage, floating product, duplicate garment, text "
                "or watermark. Keep the full person centered with hands and feet visible."
            ),
            size="1024x1536", quality="medium", output_format="png",
        )
    output.write_bytes(base64.b64decode(result.data[0].b64_json))
    return output


def generate_tryon(uid: str, request: TryOnRequest) -> dict:
    rows = []
    for garment_id in request.garment_ids:
        row = garment_store.get(uid, garment_id)
        if not row or row.get("status") != "approved" or not row.get("cutout_object"):
            raise HTTPException(409, detail={"code": "garment_not_ready", "message": "所选衣物尚未完成抠图确认。", "garment_id": garment_id})
        rows.append(row)
    if request.model_mode == "digital":
        model = body_models.get(request.body_model_id or "")
        model_path = Path(model["front_reference_path"]) if model and model.get("front_reference_path") else None
    else:
        ref = reference_store.get(uid, request.reference_photo_id or "")
        model_path = ref and object_store.materialize(ref.get("object_name", ""))
    if not model_path and settings.default_model_reference.exists():
        model_path = settings.default_model_reference
    if not model_path or not Path(model_path).exists():
        raise HTTPException(409, detail={"code": "model_reference_missing", "message": "请先生成数字衣模参考图或上传真人全身照。"})

    key = hashlib.sha256((uid + ":" + tryon_cache_key(request, str(model_path), rows)).encode()).hexdigest()
    output = settings.data_dir / "tryon" / f"{key}.png"
    if output.exists():
        object_name = object_store.upload_generated(uid, "tryon", output, f"{key}.png")
        return {"image_url": object_store.signed_read_url(object_name), "cache_hit": True, "cache_key": key}

    prompt = (
        "Create one polished full-body fashion try-on photograph. Preserve the identity, body proportions, pose and skin tone "
        "of the first reference. Dress the person in every supplied garment reference exactly once; preserve garment color, "
        "material, neckline, sleeve length, silhouette and details. Do not collage, float, duplicate or paste product images. "
        f"Scene: {request.scene}. Neutral elegant studio lighting, full body centered, hands and feet visible."
    )
    cutout_paths = [object_store.materialize(x["cutout_object"]) for x in rows]
    image_files = [open(model_path, "rb"), *[open(x, "rb") for x in cutout_paths]]
    try:
        result = client().images.edit(
            model=settings.image_model,
            image=image_files,
            prompt=prompt,
            size="1024x1536",
            quality="high" if request.quality == "final" else "medium",
            output_format="png",
        )
    finally:
        for f in image_files:
            f.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(result.data[0].b64_json))
    object_name = object_store.upload_generated(uid, "tryon", output, f"{key}.png")
    return {"image_url": object_store.signed_read_url(object_name), "cache_hit": False, "cache_key": key}
