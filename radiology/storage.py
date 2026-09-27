import logging
import os
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from time import time
from urllib.parse import urlparse
from urllib.request import urlopen

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


logger = logging.getLogger(__name__)


class CloudinaryStorageError(OSError):
    """A safe, provider-independent error raised for cloud storage failures."""


@deconstructible
class AuthenticatedCloudinaryStorage(Storage):
    """Store medical files as authenticated raw Cloudinary assets.

    Cloudinary has no local ``path`` API. SANAD materializes a permission-limited
    cache copy when DICOM validation or inference needs a filesystem path.
    """

    chunk_size = 20 * 1024 * 1024

    def __init__(self, folder, cache_location):
        self.folder = folder.strip().strip("/")
        self.cache_location = Path(cache_location)

    @staticmethod
    def _sdk():
        try:
            import cloudinary.api
            import cloudinary.exceptions
            import cloudinary.uploader
            import cloudinary.utils
        except ImportError as exc:
            raise CloudinaryStorageError(
                "Cloudinary dependencies are not installed."
            ) from exc
        return (
            cloudinary.api,
            cloudinary.exceptions,
            cloudinary.uploader,
            cloudinary.utils,
        )

    @staticmethod
    def _clean_name(name):
        normalized = str(PurePosixPath(str(name).replace("\\", "/")))
        if normalized in {"", "."} or normalized.startswith("../") or normalized.startswith("/"):
            raise ValueError("Invalid cloud storage name.")
        return normalized

    def _public_id(self, name):
        return f"{self.folder}/{self._clean_name(name)}"

    def _cache_path(self, name):
        relative = Path(*PurePosixPath(self._clean_name(name)).parts)
        root = self.cache_location.resolve()
        target = (root / relative).resolve()
        if root != target and root not in target.parents:
            raise ValueError("Invalid cloud storage cache path.")
        return target

    def _save(self, name, content):
        name = self._clean_name(name)
        _api, _exceptions, uploader, _utils = self._sdk()
        options = {
            "public_id": self._public_id(name),
            "resource_type": "raw",
            "type": "authenticated",
            "overwrite": False,
            "unique_filename": False,
            "use_filename": False,
        }
        try:
            if hasattr(content, "seek"):
                content.seek(0)
            size = getattr(content, "size", None)
            if size is not None and size > self.chunk_size:
                uploader.upload_large(content, chunk_size=self.chunk_size, **options)
            else:
                uploader.upload(content, **options)
        except Exception as exc:
            logger.exception("Cloudinary upload failed for a private medical asset.")
            raise CloudinaryStorageError("تعذر رفع الملف إلى التخزين السحابي.") from exc
        return name

    def _open(self, name, mode="rb"):
        if mode not in {"r", "rb"}:
            raise ValueError("Cloudinary medical storage is read-only after upload.")
        return File(open(self.path(name), "rb"), name=self._clean_name(name))

    def path(self, name):
        target = self._cache_path(name)
        if target.is_file():
            return str(target)

        _api, _exceptions, _uploader, utils = self._sdk()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            url = utils.private_download_url(
                self._public_id(name),
                "",
                resource_type="raw",
                type="authenticated",
                expires_at=int(time()) + 300,
                secure=True,
            )
            if urlparse(url).scheme != "https":
                raise CloudinaryStorageError("Cloudinary download URL is not HTTPS.")
            with urlopen(url, timeout=120) as response:
                maximum_size = max(
                    settings.DICOM_ZIP_MAX_UPLOAD_SIZE,
                    settings.REPORT_MAX_UPLOAD_SIZE,
                )
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > maximum_size:
                    raise CloudinaryStorageError(
                        "Cloudinary asset exceeds the configured download limit."
                    )
                with NamedTemporaryFile(
                    mode="wb", dir=target.parent, delete=False, prefix=".download-"
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    downloaded_size = 0
                    while chunk := response.read(1024 * 1024):
                        downloaded_size += len(chunk)
                        if downloaded_size > maximum_size:
                            raise CloudinaryStorageError(
                                "Cloudinary asset exceeds the configured download limit."
                            )
                        temporary.write(chunk)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, target)
        except Exception as exc:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
            logger.exception("Cloudinary download failed for a private medical asset.")
            raise CloudinaryStorageError("تعذر تنزيل الملف من التخزين السحابي.") from exc
        return str(target)

    def delete(self, name):
        if not name:
            return
        _api, _exceptions, uploader, _utils = self._sdk()
        try:
            result = uploader.destroy(
                self._public_id(name),
                resource_type="raw",
                type="authenticated",
                invalidate=True,
            )
            if result.get("result") not in {"ok", "not found"}:
                raise CloudinaryStorageError("Cloudinary did not delete the asset.")
        except Exception as exc:
            logger.exception("Cloudinary deletion failed for a private medical asset.")
            raise CloudinaryStorageError("تعذر حذف الملف من التخزين السحابي.") from exc
        self._cache_path(name).unlink(missing_ok=True)

    def exists(self, name):
        api, exceptions, _uploader, _utils = self._sdk()
        try:
            api.resource(
                self._public_id(name),
                resource_type="raw",
                type="authenticated",
            )
            return True
        except exceptions.NotFound:
            return False
        except Exception as exc:
            logger.exception("Cloudinary existence check failed.")
            raise CloudinaryStorageError("تعذر التحقق من الملف السحابي.") from exc

    def size(self, name):
        api, _exceptions, _uploader, _utils = self._sdk()
        try:
            resource = api.resource(
                self._public_id(name),
                resource_type="raw",
                type="authenticated",
            )
            return int(resource["bytes"])
        except Exception as exc:
            logger.exception("Cloudinary size lookup failed.")
            raise CloudinaryStorageError("تعذر قراءة حجم الملف السحابي.") from exc

    def url(self, name):
        raise ValueError("Private medical files do not have public URLs.")


class _PrivateMedicalStorage(Storage):
    local_setting_name = ""
    cloud_subfolder = ""

    def __init__(self, *args, **kwargs):
        # Passing a location is used by tests and explicitly requests local storage.
        explicit_location = kwargs.get("location")
        if explicit_location is not None or not settings.SANAD_CLOUDINARY_ENABLED:
            kwargs.setdefault("location", getattr(settings, self.local_setting_name))
            kwargs.setdefault("base_url", None)
            self.backend = FileSystemStorage(*args, **kwargs)
        else:
            folder = f"{settings.SANAD_CLOUDINARY_FOLDER}/{self.cloud_subfolder}"
            cache = settings.CLOUDINARY_PRIVATE_CACHE_ROOT / self.cloud_subfolder
            self.backend = AuthenticatedCloudinaryStorage(folder, cache)

    def _open(self, name, mode="rb"):
        return self.backend.open(name, mode)

    def _save(self, name, content):
        return self.backend.save(name, content)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def path(self, name):
        return self.backend.path(name)

    def url(self, name):
        raise ValueError("Private medical files do not have public URLs.")

    def get_accessed_time(self, name):
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self.backend.get_created_time(name)

    def get_modified_time(self, name):
        return self.backend.get_modified_time(name)


@deconstructible
class PrivateDicomStorage(_PrivateMedicalStorage):
    local_setting_name = "PRIVATE_DICOM_ROOT"
    cloud_subfolder = "dicom-studies"


private_dicom_storage = PrivateDicomStorage()


@deconstructible
class PrivateReportStorage(_PrivateMedicalStorage):
    local_setting_name = "PRIVATE_REPORT_ROOT"
    cloud_subfolder = "reports"


private_report_storage = PrivateReportStorage()
