from __future__ import annotations

import io
import json
import os
import shutil
import hashlib
import colorsys
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from .settings import settings

CANVAS = 1200
WARM_WHITE = (255, 253, 252, 255)
SEASONS = {"春", "夏", "秋", "冬", "春夏", "秋冬", "四季"}
CATEGORIES = {"上衣", "外套", "裤子", "裙子", "鞋", "包", "配饰", "头巾"}


def capabilities() -> dict[str, Any]:
    cuda = False
    vram_gb = 0.0
    try:
        import torch
        cuda = bool(torch.cuda.is_available())
        if cuda:
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
    except Exception:
        pass
    try:
        import rembg  # noqa: F401
        cutout_backend = "rembg"
    except Exception:
        cutout_backend = "pillow-fallback"
    tag_model = settings.model_dir / "vision"
    image_model = settings.model_dir / "qwen-image-edit"
    try:
        import transformers  # noqa: F401
        tag_runtime = True
    except Exception:
        tag_runtime = False
    try:
        import diffusers  # noqa: F401
        image_runtime = True
    except Exception:
        image_runtime = False
    return {
        "cutout": {"ready": True, "backend": cutout_backend},
        "tagging": {"ready": tag_model.exists() and tag_runtime, "backend": "local-model" if tag_model.exists() and tag_runtime else "heuristic"},
        "ai_rebuild": {
            "ready": cuda and vram_gb >= 12 and image_model.exists() and image_runtime,
            "backend": "qwen-image-edit",
            "reason": "" if cuda and vram_gb >= 12 and image_model.exists() and image_runtime else "需要兼容的 NVIDIA GPU、至少 12GB 显存、本地模型及 AI 扩展依赖",
        },
        "cuda": cuda,
        "vram_gb": vram_gb,
    }


def _open_image(source: Path) -> Image.Image:
    image = Image.open(source)
    image = ImageOps.exif_transpose(image).convert("RGBA")
    return image


def _fallback_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    corners = [rgb.getpixel((0, 0)), rgb.getpixel((rgb.width - 1, 0)), rgb.getpixel((0, rgb.height - 1)), rgb.getpixel((rgb.width - 1, rgb.height - 1))]
    bg = tuple(sum(pixel[i] for pixel in corners) // 4 for i in range(3))
    background = Image.new("RGB", rgb.size, bg)
    difference = ImageChops.difference(rgb, background).convert("L")
    mask = difference.point(lambda value: 255 if value > 18 else 0)
    mask = mask.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    bbox = mask.getbbox()
    if not bbox or (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < image.width * image.height * .03:
        return Image.new("L", image.size, 255)
    return mask


def _remove_background(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove
        result = remove(image, alpha_matting=True, alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=12, alpha_matting_erode_size=5)
        return result.convert("RGBA")
    except Exception:
        result = image.copy()
        result.putalpha(_fallback_mask(image))
        return result


def _foreground_boxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Find separated foreground groups on flat-lay/catalog backgrounds.

    This is detection only. It never claims to reconstruct hidden pixels.
    """
    try:
        import cv2
        import numpy as np
        rgba = np.asarray(image.convert("RGBA"))
        alpha = np.asarray(_remove_background(image).getchannel("A"))
        binary = (alpha > 72).astype("uint8") * 255
        scale = max(3, round(min(image.size) * .012))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (scale | 1, scale | 1))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        area = image.width * image.height
        boxes = []
        for index in range(1, count):
            x, y, width, height, pixels = map(int, stats[index])
            if pixels < area * .018 or width < image.width * .07 or height < image.height * .07:
                continue
            pad = round(max(width, height) * .045)
            boxes.append((max(0, x-pad), max(0, y-pad), min(image.width, x+width+pad), min(image.height, y+height+pad)))
        return sorted(boxes, key=lambda box: (box[1], box[0]))[:12]
    except Exception:
        return []


def _person_score(image: Image.Image) -> float:
    """Conservative local person signal using HOG and skin distribution."""
    try:
        import cv2
        import numpy as np
        rgb = np.asarray(image.convert("RGB"))
        resized = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (min(640, image.width), max(128, round(image.height * min(640, image.width) / image.width))))
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        found, weights = hog.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.05)
        hog_score = min(1.0, max([float(x) for x in weights], default=0.0) / 1.6) if len(found) else 0.0
        ycrcb = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
        skin = cv2.inRange(ycrcb, np.array([0, 133, 77], dtype=np.uint8), np.array([255, 173, 127], dtype=np.uint8))
        skin_ratio = float((skin > 0).mean())
        # Skin alone is weak evidence; it becomes meaningful in portrait-shaped photos.
        skin_score = min(1.0, max(0.0, (skin_ratio - .035) / .16)) if image.height > image.width * 1.05 else 0.0
        return max(hog_score, skin_score * .62)
    except Exception:
        return 0.0


def analyze_input_image(source: Path, filename: str = "") -> dict[str, Any]:
    image = _open_image(source)
    rgb = image.convert("RGB")
    corners = [rgb.getpixel((0, 0)), rgb.getpixel((rgb.width-1, 0)), rgb.getpixel((0, rgb.height-1)), rgb.getpixel((rgb.width-1, rgb.height-1))]
    spread = max(max(channel) - min(channel) for channel in zip(*corners))
    clean_background = spread < 30
    person = _person_score(image)
    boxes = _foreground_boxes(image) if clean_background and person < .42 else []
    hint = filename.lower()
    if person >= .7 or (person >= .42 and not clean_background) or any(word in hint for word in ("真人", "上身", "模特", "穿着", "worn", "model")):
        input_type = "worn"
        boxes = [(0, 0, image.width, image.height)]
    elif len(boxes) >= 2 or any(word in hint for word in ("整套", "穿搭", "平铺多件", "flatlay", "outfit")):
        input_type = "multi_flatlay"
        if len(boxes) < 2:
            boxes = [(0, 0, image.width, image.height)]
    elif clean_background:
        input_type = "clean_product"
        boxes = boxes[:1] or [(0, 0, image.width, image.height)]
    else:
        input_type = "complex_single"
        boxes = [(0, 0, image.width, image.height)]
    ai_required = input_type in {"worn", "complex_single"}
    return {
        "input_type": input_type,
        "ai_required": ai_required,
        "person_score": round(person, 3),
        "clean_background": clean_background,
        "detections": [
            {"index": index, "bbox": [round(x1/image.width, 5), round(y1/image.height, 5), round((x2-x1)/image.width, 5), round((y2-y1)/image.height, 5)], "confidence": .82 if input_type == "multi_flatlay" else .94}
            for index, (x1, y1, x2, y2) in enumerate(boxes)
        ],
    }


def extract_candidate(source: Path, bbox: list[float], output: Path) -> Path:
    image = _open_image(source)
    x, y, width, height = bbox
    left, top = round(x * image.width), round(y * image.height)
    right, bottom = round((x + width) * image.width), round((y + height) * image.height)
    candidate = image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate.save(output, "PNG", optimize=True)
    return output


def make_display_thumbnail(source: Path, output: Path) -> Path:
    image = _open_image(source)
    if image.getchannel("A").getextrema()[0] < 255:
        image = _compose_square(image, WARM_WHITE)
    else:
        image = ImageOps.contain(image.convert("RGB"), (CANVAS, CANVAS), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (CANVAS, CANVAS), WARM_WHITE[:3])
        canvas.paste(image, ((CANVAS-image.width)//2, (CANVAS-image.height)//2))
        image = canvas
    thumb = ImageOps.contain(image.convert("RGB"), (480, 480), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(output, "WEBP", quality=90, method=6)
    return output


def _compose_square(cutout: Image.Image, background: tuple[int, int, int, int] | None) -> Image.Image:
    bbox = cutout.getchannel("A").getbbox() or (0, 0, cutout.width, cutout.height)
    subject = cutout.crop(bbox)
    max_side = int(CANVAS * .82)
    ratio = min(max_side / max(subject.width, 1), max_side / max(subject.height, 1))
    subject = subject.resize((max(1, round(subject.width * ratio)), max(1, round(subject.height * ratio))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), background or (0, 0, 0, 0))
    x = (CANVAS - subject.width) // 2
    y = (CANVAS - subject.height) // 2
    canvas.alpha_composite(subject, (x, y))
    return canvas


def _auto_straighten(cutout: Image.Image) -> Image.Image:
    """Correct small camera tilt without inventing or repainting garment pixels."""
    alpha = cutout.getchannel("A")
    preview = ImageOps.contain(alpha, (320, 320), Image.Resampling.BILINEAR)
    base_bbox = preview.getbbox()
    if not base_bbox:
        return cutout
    base_area = max(1, (base_bbox[2]-base_bbox[0]) * (base_bbox[3]-base_bbox[1]))
    best_angle, best_area = 0, base_area
    for angle in range(-15, 16):
        if not angle:
            continue
        rotated = preview.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR)
        bbox = rotated.getbbox()
        if not bbox:
            continue
        area = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1])
        if area < best_area:
            best_angle, best_area = angle, area
    if not best_angle or best_area > base_area * .985:
        return cutout
    return cutout.rotate(best_angle, expand=True, resample=Image.Resampling.BICUBIC)


def process_image(source: Path, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    original = output_dir / ("original" + (source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".png"))
    shutil.copyfile(source, original)
    try:
        image = _open_image(source)
        normalized = output_dir / "normalized.png"
        image.save(normalized, optimize=True)
        cutout = _compose_square(_auto_straighten(_remove_background(image)), None)
        cutout_path = output_dir / "cutout.png"
        cutout.save(cutout_path, optimize=True)
        white = _compose_square(cutout, WARM_WHITE).convert("RGB")
        white_path = output_dir / "white-bg.jpg"
        white.save(white_path, quality=92, optimize=True)
        thumb = ImageOps.contain(white, (480, 480), Image.Resampling.LANCZOS)
        thumb_path = output_dir / "thumb.webp"
        thumb.save(thumb_path, "WEBP", quality=88, method=6)
        return {"original": original, "normalized": normalized, "cutout": cutout_path, "white": white_path, "thumbnail": thumb_path}
    except Exception:
        # Keep API compatibility for corrupt files while never substituting a sprite/default garment image.
        return {"original": original}


def _dominant_color_name(image_path: Path | None) -> tuple[str, float]:
    if not image_path or not image_path.exists():
        return "待确认", .0
    try:
        image = _open_image(image_path)
        image.thumbnail((220, 220))
        pixels = [pixel[:3] for pixel in image.getdata() if pixel[3] > 80 and not (pixel[0] > 242 and pixel[1] > 242 and pixel[2] > 242)]
        if not pixels:
            return "待确认", .0
        sample = Image.new("RGB", (len(pixels), 1));sample.putdata(pixels)
        colors = sample.quantize(colors=5, method=Image.Quantize.MEDIANCUT).convert("RGB").getcolors(maxcolors=8) or []
        _, (r, g, b) = max(colors, key=lambda item: item[0])
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        if v < .22:return "黑色", .82
        if s < .10:return ("白色" if v > .84 else "灰色"), .78
        if s < .22 and v > .72:return "米白色", .72
        degree = h * 360
        if degree < 12 or degree >= 345:return ("粉色" if v > .7 and s < .55 else "红色"), .74
        if degree < 35:return ("杏色" if v > .72 and s < .48 else "棕色"), .72
        if degree < 65:return "黄色", .74
        if degree < 165:return "绿色", .74
        if degree < 255:return "蓝色", .76
        if degree < 295:return "紫色", .74
        return "粉色", .72
    except Exception:
        return "待确认", .0


def heuristic_labels(filename: str, image_path: Path | None = None) -> dict[str, Any]:
    stem = Path(filename).stem.strip() or "待命名单品"
    category = "上衣"
    for keyword, value in (("外套", "外套"), ("裤", "裤子"), ("裙", "裙子"), ("鞋", "鞋"), ("包", "包"), ("头巾", "头巾"), ("配饰", "配饰")):
        if keyword in stem:
            category = value
            break
    season = next((value for value in ("春夏", "秋冬", "四季", "春", "夏", "秋", "冬") if value in stem), "四季")
    color = next((value for value in ("米白", "奶油白", "浅粉", "粉色", "藏蓝", "蓝色", "黑色", "白色", "杏色", "黄色", "绿色", "紫色", "灰色") if value in stem), "待确认")
    color_confidence = .62 if color != "待确认" else .0
    if color == "待确认":
        color, color_confidence = _dominant_color_name(image_path)
    material_defaults = {"上衣":"棉质混纺", "外套":"挺括混纺", "裤子":"织物", "裙子":"垂感面料", "鞋":"合成革", "包":"皮质", "配饰":"混合材质", "头巾":"柔软织物"}
    fit_defaults = {"上衣":"合身剪裁", "外套":"舒适廓形", "裤子":"顺直裤型", "裙子":"自然裙摆", "鞋":"舒适鞋型", "包":"实用包型", "配饰":"点缀单品", "头巾":"轻盈垂感"}
    style_defaults = {"上衣":"清新通勤", "外套":"简约通勤", "裤子":"日常简约", "裙子":"温柔简约", "鞋":"日常百搭", "包":"简约百搭", "配饰":"精致点缀", "头巾":"温柔点缀"}
    material = next((value for value in ("牛仔", "棉麻", "羊毛", "针织", "真丝", "雪纺", "皮质", "棉") if value in stem), material_defaults[category])
    fit = next((value for value in ("微喇", "阔腿", "直筒", "收腰", "修身", "宽松", "A字") if value in stem), fit_defaults[category])
    noisy_name = bool(re.search(r"^(?:\d+[_-])|来自|网页|商品图|白底图|原图|实拍|截图|小红书|淘宝|拼多多|codex|clipboard", stem, re.I))
    noun = {"上衣":"上衣", "外套":"外套", "裤子":"长裤", "裙子":"裙装", "鞋":"鞋履", "包":"包袋", "配饰":"配饰", "头巾":"头巾"}[category]
    name = (("" if color == "待确认" else color.replace("色", "")) + noun) if noisy_name else stem
    style = style_defaults[category]
    return {"name": name, "category": category, "season": season, "color": color, "material": material, "style": style, "fit": fit, "details": [], "tags": [color, material, fit][:3], "confidence": {"name": .62 if noisy_name else .55, "category": .55, "season": .5, "color": color_confidence, "material": .52, "style": .52, "fit": .52}}


def crop_image(source: Path, output_dir: Path, crop: dict[str, float]) -> dict[str, Path]:
    image = _open_image(source)
    left = max(0.0, min(1.0, float(crop.get("x", 0))))
    top = max(0.0, min(1.0, float(crop.get("y", 0))))
    width = max(.05, min(1.0 - left, float(crop.get("width", 1))))
    height = max(.05, min(1.0 - top, float(crop.get("height", 1))))
    image = image.crop((round(left * image.width), round(top * image.height), round((left + width) * image.width), round((top + height) * image.height)))
    rotation = float(crop.get("rotation", 0))
    if rotation:
        image = image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
    temporary = output_dir / "crop-source.png"
    image.save(temporary)
    result = process_image(temporary, output_dir)
    temporary.unlink(missing_ok=True)
    return result
