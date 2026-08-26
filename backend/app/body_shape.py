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
from skimage import measure

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
        return True

    @property
    def backend_name(self) -> str:
        return "official-local-rfe" if self.official_available else "continuous-implicit"

    @staticmethod
    def complete(m: BodyMeasurements, means: np.ndarray | None = None) -> dict[str, float]:
        raw = m.model_dump()
        bmi = raw["weight"] / (raw["height"] / 100) ** 2
        result = dict(raw)
        result["max_hip"] = raw["hip"]
        result["natural_waist"] = raw.get("natural_waist") or raw["waist"]
        result["arm_length"] = raw["height"] * .445
        result["crotch_to_floor"] = raw.get("leg_length") or raw["height"] * .47
        result["back_length"] = raw["height"] * .255
        result["waist_rise"] = raw["height"] * .155
        result["hand_length"] = raw["height"] * .105
        result["neck"] = raw.get("neck") or 30 + max(0, bmi - 18) * .32
        result["upper_arm"] = raw.get("upper_arm") or 22 + max(0, bmi - 18) * .55
        result["wrist"] = raw.get("wrist") or raw["height"] * .095
        result["leg_length"] = raw.get("leg_length") or raw["height"] * .58
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
        normalized = (values - model["mean"]) / np.where(model["std"] == 0, 1, model["std"])
        physical = normalized * model["std"] + model["mean"]
        mask = model["mask"].T
        matrix = model["matrix"]
        selected = np.stack([physical[row] for row in mask], axis=0)
        deformation = np.einsum("fij,fj->fi", matrix, selected).reshape(-1, 1)
        solved = model["solver"].solve(model["d2v"].T.dot(deformation))[: 12500 * 3]
        source = solved.reshape((-1, 3))
        source -= source.mean(axis=0)
        # The released mesh is Z-up with Y as the left/right axis.
        vertices = np.column_stack((source[:, 1], source[:, 2], source[:, 0]))
        # The released template carries a fixed 140-degree yaw in its source frame.
        yaw = np.deg2rad(140.0)
        vertices[:, [0, 2]] = np.column_stack((
            vertices[:, 0]*np.cos(yaw) + vertices[:, 2]*np.sin(yaw),
            -vertices[:, 0]*np.sin(yaw) + vertices[:, 2]*np.cos(yaw),
        ))
        mesh = trimesh.Trimesh(vertices=vertices, faces=model["facets"], process=False)
        return self._normalize_height(mesh, completed["height"] / 100.0)

    @staticmethod
    def _smooth_min(a: np.ndarray, b: np.ndarray, k: float = 34.0) -> np.ndarray:
        h = np.clip(.5 + .5 * (b - a) * k, 0.0, 1.0)
        return b * (1 - h) + a * h - h * (1 - h) / k

    @staticmethod
    def _ellipsoid(x, y, z, center, radius):
        rx, ry, rz = radius
        q = np.sqrt(((x-center[0])/rx)**2 + ((y-center[1])/ry)**2 + ((z-center[2])/rz)**2) - 1.0
        return q * min(radius)

    def _procedural_mesh(self, completed: dict[str, float]) -> trimesh.Trimesh:
        height = completed["height"] / 100.0
        bmi = completed["weight"] / height**2
        fat = np.clip((bmi - 18.5) / 20.0, -.15, .9)
        bust_r = completed["bust"] / 100 / (2 * np.pi * .90)
        waist_r = completed["waist"] / 100 / (2 * np.pi * .88)
        hip_r = completed["hip"] / 100 / (2 * np.pi * .90)
        thigh_r = completed["thigh"] / 100 / (2 * np.pi * .93)
        knee_r = completed["knee"] / 100 / (2 * np.pi * .96)
        shoulder_x = completed["shoulder"] / 200

        xs = np.linspace(-.48, .48, 76)
        ys = np.linspace(-.01, height + .01, 150)
        zs = np.linspace(-.30, .30, 58)
        x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")
        field = np.full(x.shape, 10.0, dtype=np.float32)

        def add(center, radius, smooth=34.0):
            nonlocal field
            field = self._smooth_min(field, self._ellipsoid(x, y, z, center, radius), smooth)

        add((0, .565*height, -.005), (hip_r*1.08, .105*height, hip_r*.73))
        add((0, .655*height, 0), (waist_r*1.04, .095*height, waist_r*.78))
        add((0, .735*height, .005), (bust_r*1.02, .105*height, bust_r*.76))
        add((0, .795*height, 0), (shoulder_x, .055*height, bust_r*.67))
        breast = max(.040, min(.075, bust_r*.38))
        for side in (-1, 1):
            add((side*bust_r*.43, .752*height, bust_r*.61), (breast*1.05, breast*.82, breast), 42)

        neck_r = completed["neck"] / 100 / (2*np.pi)
        add((0, .842*height, 0), (neck_r*1.02, .050*height, neck_r*.92))
        add((0, .915*height, -.002), (.054*height, .071*height, .047*height))
        add((0, .973*height, -.006), (.048*height, .040*height, .045*height))

        leg_x = max(.075, hip_r*.47)
        calf_r = knee_r*(1.0 + .20*fat)
        ankle_r = max(.035, completed["wrist"] / 100 / (2*np.pi) * 1.55)
        for side in (-1, 1):
            sx = side*leg_x
            add((sx, .485*height, 0), (thigh_r*1.02, .115*height, thigh_r*.88), 40)
            add((sx, .390*height, 0), (thigh_r*.92, .115*height, thigh_r*.83), 40)
            add((sx, .300*height, .002), (knee_r, .070*height, knee_r*.90), 42)
            add((sx, .215*height, -.004), (calf_r, .100*height, calf_r*.90), 40)
            add((sx, .105*height, 0), (ankle_r*1.10, .085*height, ankle_r), 40)
            add((sx, .030*height, .032), (ankle_r*1.20, .032*height, ankle_r*1.75), 40)

        upper_r = completed["upper_arm"] / 100 / (2*np.pi)
        wrist_r = completed["wrist"] / 100 / (2*np.pi)
        for side in (-1, 1):
            shoulder = side*(shoulder_x*.92)
            points = [
                (shoulder, .785*height, 0, upper_r*1.12, .060*height),
                (side*(shoulder_x+upper_r*.35), .725*height, 0, upper_r, .065*height),
                (side*(shoulder_x+upper_r*.48), .650*height, 0, upper_r*.86, .060*height),
                (side*(shoulder_x+upper_r*.52), .585*height, .003, wrist_r*1.32, .055*height),
                (side*(shoulder_x+upper_r*.50), .525*height, .008, wrist_r*1.02, .050*height),
            ]
            for px, py, pz, pr, pry in points:
                add((px, py, pz), (pr, pry, pr*.92), 42)
            add((side*(shoulder_x+upper_r*.48), .475*height, .014), (wrist_r*1.18, .042*height, wrist_r*.72), 42)

        spacing = (xs[1]-xs[0], ys[1]-ys[0], zs[1]-zs[0])
        vertices, faces, _, _ = measure.marching_cubes(field, level=0, spacing=spacing)
        vertices += np.array([xs[0], ys[0], zs[0]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        parts = mesh.split(only_watertight=False)
        mesh = max(parts, key=lambda item: item.area) if parts else mesh
        trimesh.smoothing.filter_taubin(mesh, lamb=.42, nu=-.36, iterations=7)
        return self._normalize_height(mesh, height)

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
        try:
            mesh = self._official_mesh(completed) if self.official_available else self._procedural_mesh(completed)
            backend = self.backend_name
        except Exception as exc:
            mesh = self._procedural_mesh(completed)
            backend = "continuous-implicit"
            warning.append(f"官方人体回归模型加载失败，已使用连续网格生成器：{exc}")
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
