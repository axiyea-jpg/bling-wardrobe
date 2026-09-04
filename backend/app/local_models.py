from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .local_pipeline import CATEGORIES, SEASONS, heuristic_labels
from .settings import settings


TAG_PROMPT = """分析图片中最主要的一件衣物，只输出 JSON，不要解释。
字段：name、category、season、color、material、style、fit、details、confidence。
category 只能是：上衣、外套、裤子、裙子、鞋、包、配饰、头巾。
season 只能是：春、夏、秋、冬、春夏、秋冬、四季。复合季节是独立标签。
color 只写一个主色；material 和 fit 要具体，不确定时写待确认。
confidence 是每个字段 0 到 1 的数值。"""


def _json_from_text(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("local model did not return JSON")
    return json.loads(match.group(0))


def analyze_garment(image_path: Path, filename: str) -> dict[str, Any]:
    model_path = settings.model_dir / "vision"
    if not model_path.exists():
        return heuristic_labels(filename, image_path)
    try:
        from transformers import AutoModelForCausalLM, AutoProcessor
        import torch
        processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, trust_remote_code=True, local_files_only=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        image = Image.open(image_path).convert("RGB")
        inputs = processor(text=TAG_PROMPT, images=image, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {key: value.to(model.device) if hasattr(value, "to") else value for key, value in inputs.items()}
        output = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        text = processor.batch_decode(output, skip_special_tokens=True)[0]
        result = _json_from_text(text)
    except Exception:
        return heuristic_labels(filename, image_path)
    result["category"] = result.get("category") if result.get("category") in CATEGORIES else "上衣"
    result["season"] = result.get("season") if result.get("season") in SEASONS else "四季"
    result["color"] = str(result.get("color") or "待确认").split("·")[0].split("、")[0]
    for key in ("material", "style", "fit"):
        result[key] = str(result.get(key) or "待确认")
    result["details"] = [str(value) for value in result.get("details", [])][:8]
    result["tags"] = [result["color"], result["material"], result["fit"]][:3]
    result["confidence"] = result.get("confidence") if isinstance(result.get("confidence"), dict) else {}
    return result


def rebuild_garment(image_path: Path, output_path: Path) -> Path:
    """Run Qwen Image Edit only when the user installed the optional local model."""
    import torch
    from diffusers import QwenImageEditPipeline

    model_path = settings.model_dir / "qwen-image-edit"
    if not torch.cuda.is_available() or not model_path.exists():
        raise RuntimeError("AI 重建需要兼容 GPU 与本地 Qwen Image Edit 模型")
    pipeline = QwenImageEditPipeline.from_pretrained(model_path, torch_dtype=torch.bfloat16, local_files_only=True)
    pipeline.to("cuda")
    prompt = (
        "只提取参考图中的目标衣物，将它重建为正面平铺的标准电商 2D 单品图。"
        "去除人物、皮肤、头发、手臂、腿、鞋包、背景和其他衣物；补全被身体或其他物体遮挡的衣片，"
        "但不得保留人体曲线或把人体轮廓画进衣服。严格保持真实主色、面料纹理、领型、袖型、门襟、"
        "口袋、缝线、版型和装饰。整件衣物完整可见、左右自然对称、无透视畸变，居中放在暖白纯色背景。"
    )
    result = pipeline(image=Image.open(image_path).convert("RGB"), prompt=prompt, negative_prompt="人物，人体，皮肤，脸，头发，手，腿，衣架，文字，水印，重复衣物，改变颜色，改变材质，改变版型", num_inference_steps=40, guidance_scale=4.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rebuilt = ImageOps.contain(result.images[0].convert("RGB"), (1200, 1200), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1200, 1200), (255, 253, 252))
    canvas.paste(rebuilt, ((1200-rebuilt.width)//2, (1200-rebuilt.height)//2))
    canvas.save(output_path, "PNG", optimize=True)
    return output_path
