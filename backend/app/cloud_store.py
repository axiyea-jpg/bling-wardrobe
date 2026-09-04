from __future__ import annotations

import json
import secrets
import tempfile
from datetime import timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from .settings import settings
from .sqlite_store import SqliteUserStore


class UserStore:
    """Firestore-backed user collection with an atomic JSON local adapter."""

    def __init__(self, name: str):
        self.name = name
        self.lock = RLock()
        self._firestore = None
        if settings.firestore_project_id:
            from google.cloud import firestore
            self._firestore = firestore.Client(project=settings.firestore_project_id)

    def _path(self, uid: str) -> Path:
        return settings.data_dir / "users" / uid / f"{self.name}.json"

    def _collection(self, uid: str):
        return self._firestore.collection("users").document(uid).collection(self.name)

    def list(self, uid: str) -> list[dict[str, Any]]:
        if self._firestore:
            return [dict(doc.to_dict() or {}, id=doc.id) for doc in self._collection(uid).stream()]
        path = self._path(uid)
        if not path.exists():
            return []
        return list(json.loads(path.read_text("utf-8")).values())

    def get(self, uid: str, key: str) -> dict[str, Any] | None:
        if self._firestore:
            doc = self._collection(uid).document(key).get()
            return dict(doc.to_dict() or {}, id=doc.id) if doc.exists else None
        return next((row for row in self.list(uid) if row.get("id") == key), None)

    def put(self, uid: str, key: str, value: dict[str, Any]) -> None:
        value = dict(value, id=key, user_id=uid)
        if self._firestore:
            self._collection(uid).document(key).set(value)
            return
        with self.lock:
            path = self._path(uid)
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = {row["id"]: row for row in self.list(uid)}
            rows[key] = value
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), "utf-8")
            temp.replace(path)

    def delete(self, uid: str, key: str) -> None:
        if self._firestore:
            self._collection(uid).document(key).delete()
            return
        with self.lock:
            path = self._path(uid)
            rows = {row["id"]: row for row in self.list(uid) if row.get("id") != key}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), "utf-8")


class ObjectStore:
    def __init__(self):
        self.client = self.bucket = None
        if settings.storage_bucket:
            from google.cloud import storage
            self.client = storage.Client()
            self.bucket = self.client.bucket(settings.storage_bucket)

    @property
    def cloud(self) -> bool:
        return self.bucket is not None

    def upload_target(self, uid: str, job_id: str, file_id: str, content_type: str) -> dict[str, Any]:
        object_name = f"users/{uid}/imports/{job_id}/originals/{file_id}"
        if self.cloud:
            blob = self.bucket.blob(object_name)
            url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=settings.signed_url_minutes), method="PUT", content_type=content_type)
            return {"object_name": object_name, "upload_url": url, "method": "PUT", "headers": {"Content-Type": content_type}}
        token = secrets.token_urlsafe(24)
        base = settings.public_base_url.rstrip("/") or settings.local_origin.rstrip("/") or "http://testserver"
        return {"object_name": object_name, "upload_token": token, "upload_url": f"{base}/api/import/jobs/{job_id}/files/{file_id}?upload_token={token}", "method": "PUT", "headers": {"Content-Type": content_type}}

    def local_path(self, object_name: str) -> Path:
        return settings.data_dir / "objects" / object_name

    def write_local(self, object_name: str, data: bytes) -> Path:
        path = self.local_path(object_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def materialize(self, object_name: str) -> Path:
        if not self.cloud:
            return self.local_path(object_name)
        suffix = Path(object_name).suffix or ".img"
        path = Path(tempfile.mkstemp(suffix=suffix)[1])
        self.bucket.blob(object_name).download_to_filename(path)
        return path

    def upload_generated(self, uid: str, folder: str, source: Path, name: str) -> str:
        object_name = f"users/{uid}/{folder}/{name}"
        if self.cloud:
            self.bucket.blob(object_name).upload_from_filename(source)
        else:
            target = self.local_path(object_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        return object_name

    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if self.cloud:
            self.bucket.blob(object_name).upload_from_string(data, content_type=content_type)
        else:
            self.write_local(object_name, data)
        return object_name

    def signed_read_url(self, object_name: str) -> str:
        if not object_name:
            return ""
        if self.cloud:
            return self.bucket.blob(object_name).generate_signed_url(version="v4", expiration=timedelta(minutes=settings.signed_url_minutes), method="GET")
        base = settings.public_base_url.rstrip("/") or settings.local_origin.rstrip("/")
        return f"{base}/objects/{object_name}" if base else f"/objects/{object_name}"

    def delete(self, object_name: str) -> None:
        if not object_name:
            return
        if self.cloud:
            self.bucket.blob(object_name).delete(if_generation_match=None)
        else:
            self.local_path(object_name).unlink(missing_ok=True)


Store = UserStore if settings.firestore_project_id else SqliteUserStore
garment_store = Store("garments")
job_store = Store("jobs")
reference_store = Store("references")
body_store = Store("body_models")
object_store = ObjectStore()
