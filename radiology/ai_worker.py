"""عامل مستقل لتحويل DICOM وتشغيل MONAI؛ لا يستورد Django."""

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


BLOCKED_SUFFIXES = {
    ".bat", ".cmd", ".com", ".dll", ".exe", ".js", ".msi", ".ps1", ".scr",
}


def _extract_archive(archive, destination, limits):
    extracted = []
    total_size = 0
    with zipfile.ZipFile(archive) as zipped:
        files = [item for item in zipped.infolist() if not item.is_dir()]
        if not files or len(files) > limits.max_files:
            raise ValueError("invalid archive file count")
        for item in files:
            relative = Path(item.filename.replace("\\", "/"))
            mode = item.external_attr >> 16
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or item.flag_bits & 0x1
                or stat.S_ISLNK(mode)
                or relative.suffix.lower() in BLOCKED_SUFFIXES
            ):
                raise ValueError("unsafe archive member")
            total_size += item.file_size
            if total_size > limits.max_uncompressed_size:
                raise ValueError("archive is too large")
            ratio = item.file_size / max(item.compress_size, 1)
            if ratio > limits.max_compression_ratio:
                raise ValueError("unsafe compression ratio")
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError("unsafe extraction path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(item) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            extracted.append(target)
    return extracted


def _dicom_to_nifti(dicom_root, output_path):
    import SimpleITK as sitk

    series = []
    for directory, _, _ in os.walk(dicom_root):
        for series_id in sitk.ImageSeriesReader.GetGDCMSeriesIDs(directory) or ():
            filenames = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(directory, series_id)
            if filenames:
                series.append((len(filenames), filenames))
    if not series:
        raise ValueError("no DICOM series")
    _, filenames = max(series, key=lambda item: item[0])
    reader = sitk.ImageSeriesReader()
    reader.MetaDataDictionaryArrayUpdateOff()
    reader.LoadPrivateTagsOff()
    reader.SetFileNames(filenames)
    image = reader.Execute()
    if image.GetDimension() != 3 or image.GetSize()[2] < 2:
        raise ValueError("invalid CT volume")
    sitk.WriteImage(image, str(output_path), True)


def _load_dicom_volume(dicom_root):
    import SimpleITK as sitk

    series = []
    for directory, _, _ in os.walk(dicom_root):
        for series_id in sitk.ImageSeriesReader.GetGDCMSeriesIDs(directory) or ():
            filenames = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(directory, series_id)
            if filenames:
                series.append((len(filenames), filenames))
    if not series:
        raise ValueError("no DICOM series")
    reader = sitk.ImageSeriesReader()
    reader.MetaDataDictionaryArrayUpdateOff()
    reader.LoadPrivateTagsOff()
    reader.SetFileNames(max(series, key=lambda item: item[0])[1])
    return reader.Execute()


def _render_preview(
    dicom_root,
    output_path,
    center,
    diameter_mm,
    *,
    annotate=True,
):
    import numpy as np
    import SimpleITK as sitk
    from PIL import Image, ImageDraw

    image = _load_dicom_volume(dicom_root)
    continuous_index = image.TransformPhysicalPointToContinuousIndex(center)
    x, y, z = (int(round(value)) for value in continuous_index)
    size_x, size_y, size_z = image.GetSize()
    if not (0 <= x < size_x and 0 <= y < size_y and 0 <= z < size_z):
        raise ValueError("candidate is outside image")
    pixels = sitk.GetArrayFromImage(image)[z].astype(np.float32, copy=False)
    pixels = np.clip((pixels + 1000.0) / 1400.0, 0.0, 1.0)
    pixels = (pixels * 255).astype(np.uint8)
    preview = Image.fromarray(pixels, mode="L").convert("RGB")
    spacing_x, spacing_y, _ = image.GetSpacing()
    radius = max(8, int(round((float(diameter_mm) / 2) / min(spacing_x, spacing_y))))
    if annotate:
        draw = ImageDraw.Draw(preview)
        line_width = max(2, preview.width // 170)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(255, 55, 65), width=line_width)
        crosshair = radius + 8
        draw.line((x - crosshair, y, x + crosshair, y), fill=(255, 55, 65), width=line_width)
        draw.line((x, y - crosshair, x, y + crosshair), fill=(255, 55, 65), width=line_width)
    preview.save(output_path, format="PNG", optimize=True)
    return {
        "center_index": {"x": x, "y": y, "z": z},
        "image_size": {"width": size_x, "height": size_y, "depth": size_z},
        "origin": list(image.GetOrigin()),
        "spacing": list(image.GetSpacing()),
        "direction": list(image.GetDirection()),
    }


def _run_bundle(bundle_root, runtime_root, dataset_path):
    result_path = runtime_root / "results.json"
    command = [
        sys.executable,
        "-m",
        "monai.bundle",
        "run",
        "--config_file",
        str(bundle_root / "configs" / "inference.json"),
        "--bundle_root",
        str(bundle_root),
        "--dataset_dir",
        str(runtime_root),
        "--data_list_file_path",
        str(dataset_path),
        "--output_dir",
        str(runtime_root),
        "--output_filename",
        result_path.name,
        "--dataloader#num_workers",
        "0",
    ]
    completed = subprocess.run(
        command,
        cwd=bundle_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0 or not result_path.is_file():
        raise RuntimeError("MONAI inference failed")
    results = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("invalid MONAI result")
    return results[0]


def _candidate_payload(result):
    boxes = result.get("box", [])
    scores = result.get("label_scores", [])
    labels = result.get("label", [])
    if not (isinstance(boxes, list) and len(boxes) == len(scores) == len(labels)):
        raise ValueError("inconsistent MONAI result")
    candidates = []
    for box, score, label in zip(boxes, scores, labels):
        if not isinstance(box, list) or len(box) != 6:
            raise ValueError("invalid MONAI box")
        center_x, center_y, center_z, width, height, depth = map(float, box)
        score = float(score)
        if not 0 <= score <= 1:
            raise ValueError("invalid MONAI score")
        original = {"box": box, "box_mode": "cccwhd", "label": label, "score": score}
        candidates.append(
            {
                "score": score,
                "coordinates": {
                    "space": "world_mm_from_monai_bundle",
                    "box_mode": "cccwhd",
                    "center": {"x": center_x, "y": center_y, "z": center_z},
                },
                "measurements": {
                    "width_mm": width,
                    "height_mm": height,
                    "depth_mm": depth,
                    "maximum_dimension_mm": max(width, height, depth),
                },
                "original_output": original,
            }
        )
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--preview-output", type=Path)
    parser.add_argument("--preview-metadata-output", type=Path)
    parser.add_argument("--plain-preview", action="store_true")
    parser.add_argument("--center-x", type=float)
    parser.add_argument("--center-y", type=float)
    parser.add_argument("--center-z", type=float)
    parser.add_argument("--diameter-mm", type=float)
    parser.add_argument("--max-files", type=int, required=True)
    parser.add_argument("--max-uncompressed-size", type=int, required=True)
    parser.add_argument("--max-compression-ratio", type=float, required=True)
    limits = parser.parse_args()
    if not limits.archive.is_file():
        raise ValueError("required input is unavailable")
    with tempfile.TemporaryDirectory(prefix="sanad_ai_") as temporary:
        runtime_root = Path(temporary)
        dicom_root = runtime_root / "dicom"
        dicom_root.mkdir()
        _extract_archive(limits.archive, dicom_root, limits)
        if limits.preview_output:
            coordinates = (limits.center_x, limits.center_y, limits.center_z)
            if None in coordinates or limits.diameter_mm is None:
                raise ValueError("preview coordinates are required")
            metadata = _render_preview(
                dicom_root,
                limits.preview_output,
                coordinates,
                limits.diameter_mm,
                annotate=not limits.plain_preview,
            )
            if limits.preview_metadata_output:
                limits.preview_metadata_output.write_text(
                    json.dumps(metadata, separators=(",", ":")),
                    encoding="utf-8",
                )
            return
        if not limits.bundle_root or not (limits.bundle_root / "models" / "model.pt").is_file():
            raise ValueError("model bundle is unavailable")
        nifti_path = runtime_root / "ct.nii.gz"
        _dicom_to_nifti(dicom_root, nifti_path)
        dataset_path = runtime_root / "dataset.json"
        dataset_path.write_text(
            json.dumps({"validation": [{"image": nifti_path.name}]}),
            encoding="utf-8",
        )
        result = _run_bundle(limits.bundle_root, runtime_root, dataset_path)
        payload = {"candidates": _candidate_payload(result)}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
