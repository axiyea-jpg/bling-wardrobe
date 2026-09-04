from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

import numpy as np
import scipy.sparse
import scipy.sparse.linalg
import trimesh
from PIL import Image, ImageDraw

from .cloud_store import body_store, object_store
from .schemas import BodyMeasurements, BodyModelResult
from .settings import settings


MEASUREMENT_ORDER = [
    "weight", "height", "neck", "bust", "waist", "hip", "arm_length",
    "crotch_to_floor", "shoulder", "back_length", "natural_waist", "max_hip",
    "waist_rise", "hand_length", "upper_arm", "wrist", "leg_length", "knee", "thigh",
]

OFFICIAL_FILES = (
    "facets.npy", "normals.npy", "female_rfemask.npy", "female_rfemat.npy",
    "female_d2v.npz", "female_mean_measure.npy", "female_std_measure.npy",
)


class AnthropometricBodyService:
    """Generate one continuous female body mesh and export a real binary GLB."""

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._lock = threading.Lock()
        self._official = None

    @property
    def official_available(self) -> bool:
        return all((self.model_dir / name).exists() for name in OFFICIAL_FILES)

    @property
    def available(self) -> bool:
        return self.official_available

    @property
    def backend_name(self) -> str:
        return "official-local-rfe" if self.official_available else "unavailable"

    @staticmethod
    def complete(m: BodyMeasurements, means: np.ndarray | None = None) -> dict[str, float]:
        raw = m.model_dump()
        bmi = raw["weight"] / (raw["height"] / 100) ** 2
        result = dict(raw)
        result["max_hip"] = raw["hip"]
        result["natural_waist"] = raw.get("natural_waist") or raw["waist"]
        # Keep the released model's 19 measurements in their original meaning.
        # Index 6 is neck -> shoulder -> elbow -> wrist, while index 13 is
        # shoulder -> mid-hand (it is not the hand length).
        result["arm_length"] = raw["height"] * .445
        result["crotch_to_floor"] = raw.get("leg_length") or raw["height"] * .47
        result["back_length"] = raw["height"] * .445
        # In the SPRING measurement table this is a full natural-waist rise,
        # not a short vertical waist-to-crotch distance.
        result["waist_rise"] = raw["hip"] * 1.02
        result["hand_length"] = raw["height"] * .35
        result["neck"] = raw.get("neck") or 30 + max(0, bmi - 18) * .32
        result["upper_arm"] = raw.get("upper_arm") or 22 + max(0, bmi - 18) * .55
        result["wrist"] = raw.get("wrist") or raw["height"] * .095
        result["leg_length"] = raw.get("leg_length") or raw["height"] * .72
        result["knee"] = raw.get("knee") or 31 + max(0, bmi - 18) * .35
        result["thigh"] = raw.get("thigh") or 43 + max(0, bmi - 18) * 1.05
        return {key: float(value) for key, value in result.items() if value is not None}

    def _load_official(self) -> dict:
        if self._official is not None:
            return self._official
        with self._lock:
            if self._official is not None:
                return self._official
            loader = np.load(self.model_dir / "female_d2v.npz")
            d2v = scipy.sparse.coo_matrix(
                (loader["data"], (loader["row"], loader["col"])), shape=loader["shape"]
            ).tocsr()
            self._official = {
                "facets": np.load(self.model_dir / "facets.npy").astype(np.int64) - 1,
                "normals": np.load(self.model_dir / "normals.npy"),
                "mask": np.load(self.model_dir / "female_rfemask.npy").astype(bool),
                "matrix": np.load(self.model_dir / "female_rfemat.npy", allow_pickle=True),
                "mean": np.load(self.model_dir / "female_mean_measure.npy").reshape(-1),
                "std": np.load(self.model_dir / "female_std_measure.npy").reshape(-1),
                "d2v": d2v,
                "solver": scipy.sparse.linalg.splu((d2v.T @ d2v).tocsc()),
            }
            return self._official

    def _official_mesh(self, completed: dict[str, float]) -> trimesh.Trimesh:
        model = self._load_official()
        values = np.array([completed[key] for key in MEASUREMENT_ORDER], dtype=np.float64)
        values[0] = np.cbrt(values[0]) * 1000.0
        values[1:] *= 10.0
        mask = model["mask"].T
        matrix = model["matrix"]
        # reshaper.py mapping_rfemat() first converts the normalized vector
        # back to physical measurements, then selects the facet-local values.
        # `values` is already in those physical units after completion.
        selected = np.stack([values[row] for row in mask], axis=0)
        deformation = np.einsum("fij,fj->fi", matrix, selected).reshape(-1, 1)
        solved = model["solver"].solve(model["d2v"].T.dot(deformation))[: 12500 * 3]
        source = solved.reshape((-1, 3))
        source -= source.mean(axis=0)
        # The released mesh is Z-up. Preserve its native orientation; the old
        # hard-coded 140 degree yaw mixed body width with depth and made the
        # front view unnaturally broad.
        vertices = np.column_stack((-source[:, 1], source[:, 2], source[:, 0]))
        # Align the template's native diagonal pose to a true front-facing GLB
        # so the first camera view matches the released demo.
        yaw = np.deg2rad(45.0)
        vertices[:, [0, 2]] = np.column_stack((
            vertices[:, 0] * np.cos(yaw) + vertices[:, 2] * np.sin(yaw),
            -vertices[:, 0] * np.sin(yaw) + vertices[:, 2] * np.cos(yaw),
        ))
        mesh = trimesh.Trimesh(vertices=vertices, faces=model["facets"], process=False)
        return self._normalize_height(mesh, completed["height"] / 100.0)

    @staticmethod
    def _normalize_height(mesh: trimesh.Trimesh, target_height: float) -> trimesh.Trimesh:
        bounds = mesh.bounds
        current = bounds[1, 1] - bounds[0, 1]
        if current <= 0 or not np.isfinite(current):
            raise ValueError("Generated mesh has invalid height")
        vertices = mesh.vertices.copy()
        vertices[:, 1] = (vertices[:, 1] - bounds[0, 1]) * (target_height / current)
        vertices[:, 0] -= (vertices[:, 0].min() + vertices[:, 0].max()) / 2
        vertices[:, 2] -= (vertices[:, 2].min() + vertices[:, 2].max()) / 2
        mesh.vertices = vertices
        mesh.remove_unreferenced_vertices()
        mesh.fix_normals()
        material = trimesh.visual.material.PBRMaterial(
            baseColorFactor=[116, 132, 224, 255], metallicFactor=0.0, roughnessFactor=.78
        )
        mesh.visual = trimesh.visual.TextureVisuals(material=material)
        return mesh

    @staticmethod
    def _render_reference(mesh: trimesh.Trimesh, output: Path, angle: float) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (512, 768), (23, 25, 29))
        draw = ImageDraw.Draw(image)
        vertices = np.asarray(mesh.vertices).copy()
        center = (mesh.bounds[0] + mesh.bounds[1]) / 2
        vertices -= center
        c, s = np.cos(angle), np.sin(angle)
        vertices[:, [0, 2]] = np.column_stack((vertices[:, 0]*c + vertices[:, 2]*s, -vertices[:, 0]*s + vertices[:, 2]*c))
        scale = min(440 / max(np.ptp(vertices[:, 0]), .01), 680 / max(np.ptp(vertices[:, 1]), .01))
        projected = np.column_stack((256 + vertices[:, 0]*scale, 385 - vertices[:, 1]*scale))
        faces = np.asarray(mesh.faces)
        depth = vertices[faces, 2].mean(axis=1)
        normals = np.cross(vertices[faces[:, 1]]-vertices[faces[:, 0]], vertices[faces[:, 2]]-vertices[faces[:, 0]])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        light = np.array([-.35, .55, .76])
        shade = np.clip(normals @ light, -.15, 1.0)
        for index in np.argsort(depth):
            if normals[index, 2] < 0:
                continue
            value = int(138 + 72*shade[index])
            color = (int(value*.78), int(value*.84), min(255, value+34))
            draw.polygon([tuple(point) for point in projected[faces[index]]], fill=color)
        image.save(output, "PNG", optimize=True)

    def generate(self, measurements: BodyMeasurements, uid: str = "local-owner") -> BodyModelResult:
        completed = self.complete(measurements)
        warning = []
        if not self.official_available:
            raise RuntimeError("官方人体回归模型文件不完整，已停止生成，避免显示错误的程序化人体")
        mesh = self._official_mesh(completed)
        backend = self.backend_name
        if not np.isfinite(mesh.vertices).all() or len(mesh.vertices) < 1000:
            raise ValueError("Generated body mesh is invalid")

        body_id = uuid.uuid4().hex
        out_dir = settings.data_dir / "body-models" / uid / body_id
        out_dir.mkdir(parents=True, exist_ok=True)
        glb_path, front_path, three_path = out_dir / "body.glb", out_dir / "front.png", out_dir / "three-quarter.png"
        glb_path.write_bytes(mesh.export(file_type="glb"))
        self._render_reference(mesh, front_path, 0.0)
        self._render_reference(mesh, three_path, np.deg2rad(32))

        glb_object = object_store.upload_generated(uid, "body-models", glb_path, f"{body_id}.glb")
        front_object = object_store.upload_generated(uid, "body-models", front_path, f"{body_id}-front.png")
        three_object = object_store.upload_generated(uid, "body-models", three_path, f"{body_id}-three-quarter.png")
        metadata = {
            "id": body_id, "measurements": completed, "backend": backend,
            "glb_object": glb_object, "front_reference_object": front_object,
            "three_quarter_reference_object": three_object,
        }
        body_store.put(uid, body_id, metadata)
        (out_dir / "profile.json").write_text(json.dumps(metadata, ensure_ascii=False), "utf-8")
        return BodyModelResult(
            body_model_id=body_id, completed_measurements=completed,
            glb_url=object_store.signed_read_url(glb_object),
            front_reference_url=object_store.signed_read_url(front_object),
            three_quarter_reference_url=object_store.signed_read_url(three_object), warnings=warning,
        )


body_service = AnthropometricBodyService(settings.model_dir)
