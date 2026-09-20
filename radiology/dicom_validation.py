import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import pydicom
from django.conf import settings
from pydicom.errors import InvalidDicomError
from pydicom.uid import UID


class DicomStudyValidationError(Exception):
    """خطأ آمن يمكن عرضه للمستخدم دون كشف محتوى DICOM."""


@dataclass(frozen=True)
class DicomStudyMetadata:
    study_instance_uid: str
    modality: str
    study_date: object
    slice_count: int


BLOCKED_EXTENSIONS = {
    ".bat", ".cmd", ".com", ".dll", ".exe", ".html", ".hta", ".js",
    ".msi", ".ps1", ".py", ".scr", ".sh", ".vbs",
}
REQUIRED_TAGS = ["StudyInstanceUID", "SOPInstanceUID", "Modality", "StudyDate"]


def _safe_member_path(filename):
    if not filename or "\x00" in filename:
        raise DicomStudyValidationError("يحتوي الملف المضغوط على مسار غير صالح.")
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in ("", ".") for part in path.parts)
    ):
        raise DicomStudyValidationError("يحتوي الملف المضغوط على مسار غير آمن.")
    if path.suffix.lower() in BLOCKED_EXTENSIONS:
        raise DicomStudyValidationError("يحتوي الملف المضغوط على محتوى غير مسموح.")
    return path


def _inspect_archive(archive):
    members = [item for item in archive.infolist() if not item.is_dir()]
    if not members:
        raise DicomStudyValidationError("ملف ZIP فارغ ولا يحتوي على شرائح DICOM.")
    if len(members) > settings.DICOM_ZIP_MAX_FILES:
        raise DicomStudyValidationError("تجاوز عدد الملفات داخل الدراسة الحد المسموح.")

    total_size = 0
    total_compressed = 0
    safe_paths = []
    seen_paths = set()
    for member in members:
        safe_path = _safe_member_path(member.filename)
        normalized = safe_path.as_posix().casefold()
        if normalized in seen_paths:
            raise DicomStudyValidationError("يحتوي ملف ZIP على أسماء ملفات مكررة.")
        seen_paths.add(normalized)
        unix_mode = (member.external_attr >> 16) & 0o170000
        if unix_mode == stat.S_IFLNK:
            raise DicomStudyValidationError("لا يُسمح بالروابط الرمزية داخل ملف ZIP.")
        if member.flag_bits & 0x1:
            raise DicomStudyValidationError("لا يمكن قبول ملف ZIP مشفر.")
        total_size += member.file_size
        total_compressed += member.compress_size
        if total_size > settings.DICOM_ZIP_MAX_UNCOMPRESSED_SIZE:
            raise DicomStudyValidationError("تجاوز الحجم بعد فك الضغط الحد المسموح.")
        if member.file_size and not member.compress_size:
            raise DicomStudyValidationError("نسبة ضغط الملف غير آمنة.")
        if member.compress_size and member.file_size / member.compress_size > settings.DICOM_ZIP_MAX_COMPRESSION_RATIO:
            raise DicomStudyValidationError("نسبة ضغط الملف غير آمنة.")
        safe_paths.append((member, safe_path))

    if total_compressed and total_size / total_compressed > settings.DICOM_ZIP_MAX_COMPRESSION_RATIO:
        raise DicomStudyValidationError("نسبة ضغط الدراسة غير آمنة.")
    return safe_paths


def _extract_safely(archive, members, destination):
    destination = Path(destination).resolve()
    actual_size = 0
    extracted_files = []
    for member, relative_path in members:
        target = (destination / Path(*relative_path.parts)).resolve()
        if not target.is_relative_to(destination):
            raise DicomStudyValidationError("يحتوي الملف المضغوط على مسار غير آمن.")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(member, "r") as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    actual_size += len(chunk)
                    if actual_size > settings.DICOM_ZIP_MAX_UNCOMPRESSED_SIZE:
                        raise DicomStudyValidationError("تجاوز الحجم بعد فك الضغط الحد المسموح.")
                    output.write(chunk)
        except (RuntimeError, OSError, EOFError, zipfile.BadZipFile) as exc:
            raise DicomStudyValidationError("تعذر فك ملف ZIP بصورة آمنة.") from exc
        extracted_files.append(target)
    return extracted_files


def _read_dicom_metadata(file_path):
    try:
        try:
            dataset = pydicom.dcmread(
                file_path,
                stop_before_pixels=True,
                specific_tags=REQUIRED_TAGS,
            )
        except InvalidDicomError:
            dataset = pydicom.dcmread(
                file_path,
                stop_before_pixels=True,
                force=True,
                specific_tags=REQUIRED_TAGS,
            )
    except Exception as exc:  # parser boundary: never expose library/file details
        raise DicomStudyValidationError("يحتوي ملف ZIP على ملف غير صالح أو غير مسموح.") from exc

    study_uid = str(getattr(dataset, "StudyInstanceUID", "")).strip()
    sop_uid = str(getattr(dataset, "SOPInstanceUID", "")).strip()
    modality = str(getattr(dataset, "Modality", "")).strip().upper()
    if not study_uid or not sop_uid or not UID(study_uid).is_valid or not UID(sop_uid).is_valid:
        raise DicomStudyValidationError("يحتوي ملف ZIP على ملف غير صالح أو غير مسموح.")
    if modality != "CT":
        raise DicomStudyValidationError("الدراسة المرفوعة ليست دراسة أشعة مقطعية CT.")
    return study_uid, modality, str(getattr(dataset, "StudyDate", "")).strip()


def validate_dicom_zip(zip_path):
    if not zipfile.is_zipfile(zip_path):
        raise DicomStudyValidationError("الملف المرفوع ليس ملف ZIP صالحًا.")

    try:
        with zipfile.ZipFile(zip_path, "r") as archive, TemporaryDirectory(prefix="sanad_dicom_") as temp_dir:
            members = _inspect_archive(archive)
            files = _extract_safely(archive, members, temp_dir)
            study_uids = set()
            study_date = None
            for file_path in files:
                uid, modality, raw_date = _read_dicom_metadata(file_path)
                study_uids.add(uid)
                if raw_date and study_date is None:
                    try:
                        study_date = datetime.strptime(raw_date, "%Y%m%d").date()
                    except ValueError:
                        study_date = None
            if len(study_uids) != 1:
                raise DicomStudyValidationError("يجب أن تنتمي جميع الشرائح إلى دراسة DICOM واحدة.")
            return DicomStudyMetadata(
                study_instance_uid=study_uids.pop(),
                modality="CT",
                study_date=study_date,
                slice_count=len(files),
            )
    except DicomStudyValidationError:
        raise
    except (OSError, RuntimeError, EOFError, zipfile.BadZipFile) as exc:
        raise DicomStudyValidationError("تعذر قراءة ملف ZIP المرفوع بأمان.") from exc
