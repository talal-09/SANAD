import hashlib
import json
import math
import os
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings

from .services import AnalysisResult, CandidateResult


class MonaiLungNoduleBackend:
    """تشغيل حزمة MONAI في بيئة Python المعزولة عن بيئة Django."""

    model_name = "MONAI Lung Nodule CT Detection"
    model_version = "0.6.9"

    def analyze(self, dicom_zip_path: Path) -> AnalysisResult:
        python_path = Path(settings.SANAD_AI_PYTHON)
        worker_path = Path(__file__).with_name("ai_worker.py")
        bundle_path = Path(settings.SANAD_AI_MODEL_ROOT)
        model_path = bundle_path / "models" / "model.pt"
        for required_path in (python_path, worker_path, model_path):
            if not required_path.is_file():
                raise RuntimeError("AI runtime component is unavailable")

        command = [
            str(python_path),
            str(worker_path),
            "--archive",
            str(dicom_zip_path),
            "--bundle-root",
            str(bundle_path),
            "--max-files",
            str(settings.DICOM_ZIP_MAX_FILES),
            "--max-uncompressed-size",
            str(settings.DICOM_ZIP_MAX_UNCOMPRESSED_SIZE),
            "--max-compression-ratio",
            str(settings.DICOM_ZIP_MAX_COMPRESSION_RATIO),
        ]
        run_options = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "timeout": settings.SANAD_AI_TIMEOUT_SECONDS,
            "check": False,
        }
        if os.name == "nt":
            run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(command, **run_options)
        if completed.returncode != 0 or len(completed.stdout) > 10_000_000:
            raise RuntimeError("AI worker failed")
        try:
            payload = json.loads(completed.stdout)
            raw_candidates = payload["candidates"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("AI worker returned invalid output") from exc
        if not isinstance(raw_candidates, list):
            raise RuntimeError("AI worker returned invalid candidates")

        candidates = tuple(
            CandidateResult(
                source_candidate_id=f"monai-{index:04d}",
                confidence_score=Decimal(str(item["score"])).quantize(
                    Decimal("0.0001")
                ),
                coordinates=item["coordinates"],
                measurements=item["measurements"],
                original_output=item["original_output"],
            )
            for index, item in enumerate(raw_candidates, start=1)
        )
        return AnalysisResult(
            model_name=self.model_name,
            model_version=self.model_version,
            candidates=candidates,
        )


def _preview_cache_paths(dicom_zip_path, center, diameter_mm, annotate):
    archive = Path(dicom_zip_path)
    try:
        archive_stat = archive.stat()
        archive_version = [archive_stat.st_size, archive_stat.st_mtime_ns]
    except OSError:
        archive_version = [None, None]
    fingerprint = json.dumps(
        {
            "archive": str(archive.resolve()),
            "archive_version": archive_version,
            "center": center,
            "diameter_mm": str(diameter_mm),
            "annotate": annotate,
            "renderer_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    cache_key = hashlib.sha256(fingerprint).hexdigest()
    cache_root = Path(settings.PRIVATE_PREVIEW_CACHE_ROOT)
    return cache_root, cache_root / f"{cache_key}.png", cache_root / f"{cache_key}.json"


def _read_cached_preview(image_path, metadata_path):
    try:
        image = image_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 10_000_000:
        return None
    if not isinstance(metadata, dict):
        return None
    return image, metadata


def _write_private_cache_file(path, content, *, text=False):
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        if text:
            temporary_path.write_text(content, encoding="utf-8")
        else:
            temporary_path.write_bytes(content)
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _cache_preview(cache_root, image_path, metadata_path, image, metadata):
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        _write_private_cache_file(image_path, image)
        _write_private_cache_file(
            metadata_path,
            json.dumps(metadata, separators=(",", ":")),
            text=True,
        )
        cached_images = list(cache_root.glob("*.png"))
        overflow = len(cached_images) - settings.PREVIEW_CACHE_MAX_ENTRIES
        if overflow > 0:
            oldest = sorted(cached_images, key=lambda path: path.stat().st_mtime)[:overflow]
            for old_image in oldest:
                old_image.unlink(missing_ok=True)
                old_image.with_suffix(".json").unlink(missing_ok=True)
    except OSError:
        # A cache failure must not block access to the protected medical preview.
        return


def _render_candidate_preview(dicom_zip_path, center, diameter_mm, *, annotate):
    """أنشئ صورة محمية مؤقتة لشريحة المرشح دون حفظها في MEDIA_ROOT."""
    cache_root, cached_image_path, cached_metadata_path = _preview_cache_paths(
        dicom_zip_path, center, diameter_mm, annotate
    )
    cached = _read_cached_preview(cached_image_path, cached_metadata_path)
    if cached:
        return cached
    python_path = Path(settings.SANAD_AI_PYTHON)
    worker_path = Path(__file__).with_name("ai_worker.py")
    if not python_path.is_file() or not worker_path.is_file():
        raise RuntimeError("AI preview runtime is unavailable")
    with tempfile.TemporaryDirectory(prefix="sanad_preview_") as temporary:
        output_path = Path(temporary) / "preview.png"
        metadata_path = Path(temporary) / "preview.json"
        command = [
            str(python_path), str(worker_path),
            "--archive", str(dicom_zip_path),
            "--preview-output", str(output_path),
            "--preview-metadata-output", str(metadata_path),
            "--center-x", str(center["x"]),
            "--center-y", str(center["y"]),
            "--center-z", str(center["z"]),
            "--diameter-mm", str(diameter_mm),
            "--max-files", str(settings.DICOM_ZIP_MAX_FILES),
            "--max-uncompressed-size", str(settings.DICOM_ZIP_MAX_UNCOMPRESSED_SIZE),
            "--max-compression-ratio", str(settings.DICOM_ZIP_MAX_COMPRESSION_RATIO),
        ]
        if not annotate:
            command.append("--plain-preview")
        run_options = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 120,
            "check": False,
        }
        if os.name == "nt":
            run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(command, **run_options)
        if (
            completed.returncode != 0
            or not output_path.is_file()
            or not metadata_path.is_file()
        ):
            raise RuntimeError("AI preview worker failed")
        image = output_path.read_bytes()
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 10_000_000:
            raise RuntimeError("AI preview output is invalid")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("AI preview metadata is invalid") from exc
        _cache_preview(
            cache_root,
            cached_image_path,
            cached_metadata_path,
            image,
            metadata,
        )
        return image, metadata


def render_candidate_preview(dicom_zip_path, center, diameter_mm):
    image, _metadata = _render_candidate_preview(
        dicom_zip_path,
        center,
        diameter_mm,
        annotate=True,
    )
    return image


def render_candidate_editor_preview(dicom_zip_path, center, diameter_mm):
    return _render_candidate_preview(
        dicom_zip_path,
        center,
        diameter_mm,
        annotate=False,
    )


def preview_pixel_to_physical_point(metadata, pixel_x, pixel_y):
    """حوّل موضعًا على الشريحة المعروضة إلى نقطة DICOM بالملليمتر."""
    center = metadata["center_index"]
    size = metadata["image_size"]
    origin = metadata["origin"]
    spacing = metadata["spacing"]
    direction = metadata["direction"]
    values = [pixel_x, pixel_y, center["z"]]
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("invalid correction point")
    if not (0 <= float(pixel_x) < size["width"] and 0 <= float(pixel_y) < size["height"]):
        raise ValueError("correction point is outside preview")
    if len(origin) != 3 or len(spacing) != 3 or len(direction) != 9:
        raise ValueError("invalid preview geometry")
    scaled = [float(values[index]) * float(spacing[index]) for index in range(3)]
    physical = [
        float(origin[row])
        + sum(float(direction[row * 3 + column]) * scaled[column] for column in range(3))
        for row in range(3)
    ]
    return {
        "space": "world_mm_from_dicom_correction",
        "center": dict(zip(("x", "y", "z"), physical)),
        "source_preview_pixel": {
            "x": float(pixel_x),
            "y": float(pixel_y),
            "z": float(center["z"]),
        },
    }
