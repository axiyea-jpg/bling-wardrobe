InvalidOperation: 
Line |
   2 |  [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Literal ��
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot set property. Property setting is supported only on core types in this language mode.
import hashlib
from pathlib import Path
from fastapi import UploadFile

from .settings import settings


async def save_upload(upload: UploadFile, folder: str) -> tuple[Path, str]:
    raw = await upload.read()
    digest = hashlib.sha256(raw).hexdigest()
    suffix = Path(upload.filename or "image.png").suffix.lower() or ".png"
    target_dir = settings.data_dir / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{digest}{suffix}"
    if not target.exists():
        target.write_bytes(raw)
    return target, digest


def public_url(path: Path) -> str:
    rel = path.relative_to(settings.data_dir).as_posix()
    return f"{settings.public_base_url.rstrip('/')}/files/{rel}" if settings.public_base_url else f"/files/{rel}"


