import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from .settings import settings


class JsonStore:
    """Small single-user store; replace with Firestore without changing API schemas."""

    def __init__(self, name: str):
        self.path = settings.data_dir / f"{name}.json"
        self.lock = RLock()

    def all(self) -> dict[str, Any]:
        with self.lock:
            if not self.path.exists():
                return {}
            return json.loads(self.path.read_text("utf-8"))

    def get(self, key: str) -> Any | None:
        return self.all().get(key)

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            data = self.all()
            data[key] = value
            self._write(data)

    def delete(self, key: str) -> None:
        with self.lock:
            data = self.all()
            data.pop(key, None)
            self._write(data)

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.path)
        finally:
            Path(tmp).unlink(missing_ok=True)


jobs = JsonStore("jobs")
garments = JsonStore("garments")
body_models = JsonStore("body_models")
references = JsonStore("references")

