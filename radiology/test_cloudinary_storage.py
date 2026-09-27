from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .storage import (
    AuthenticatedCloudinaryStorage,
    PrivateDicomStorage,
)


class _DownloadResponse(BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AuthenticatedCloudinaryStorageTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage = AuthenticatedCloudinaryStorage(
            "sanad/private-medical/reports",
            self.temporary_directory.name,
        )

    def test_uploads_as_authenticated_raw_asset(self):
        uploader = mock.Mock()
        sdk = (mock.Mock(), mock.Mock(), uploader, mock.Mock())
        with mock.patch.object(self.storage, "_sdk", return_value=sdk):
            name = self.storage._save("2026/09/report.pdf", ContentFile(b"%PDF-1.7"))

        self.assertEqual(name, "2026/09/report.pdf")
        uploader.upload.assert_called_once()
        options = uploader.upload.call_args.kwargs
        self.assertEqual(options["resource_type"], "raw")
        self.assertEqual(options["type"], "authenticated")
        self.assertFalse(options["overwrite"])
        self.assertEqual(
            options["public_id"],
            "sanad/private-medical/reports/2026/09/report.pdf",
        )

    def test_download_uses_temporary_signed_https_url_and_private_cache(self):
        utils = mock.Mock()
        utils.private_download_url.return_value = "https://api.cloudinary.com/download?signed=1"
        sdk = (mock.Mock(), mock.Mock(), mock.Mock(), utils)
        with (
            mock.patch.object(self.storage, "_sdk", return_value=sdk),
            mock.patch(
                "radiology.storage.urlopen",
                return_value=_DownloadResponse(b"private-report"),
            ) as download,
        ):
            path = Path(self.storage.path("2026/09/report.pdf"))

        self.assertEqual(path.read_bytes(), b"private-report")
        download.assert_called_once_with(
            "https://api.cloudinary.com/download?signed=1", timeout=120
        )
        self.assertEqual(
            utils.private_download_url.call_args.kwargs["type"], "authenticated"
        )

    def test_rejects_parent_directory_traversal(self):
        with self.assertRaises(ValueError):
            self.storage.path("../secret.pdf")

    def test_never_exposes_a_public_url(self):
        with self.assertRaises(ValueError):
            self.storage.url("report.pdf")


class PrivateStorageSelectionTests(SimpleTestCase):
    @override_settings(
        SANAD_CLOUDINARY_ENABLED=True,
        SANAD_CLOUDINARY_FOLDER="sanad/private-medical",
        CLOUDINARY_PRIVATE_CACHE_ROOT=Path("private-cache"),
    )
    def test_cloudinary_backend_is_selected_when_enabled(self):
        storage = PrivateDicomStorage()
        self.assertIsInstance(storage.backend, AuthenticatedCloudinaryStorage)
        self.assertEqual(
            storage.backend.folder,
            "sanad/private-medical/dicom-studies",
        )

    @override_settings(SANAD_CLOUDINARY_ENABLED=True)
    def test_explicit_location_keeps_tests_and_tools_local(self):
        with TemporaryDirectory() as location:
            storage = PrivateDicomStorage(location=location, base_url=None)
            name = storage.save("study.zip", ContentFile(b"zip"))
            self.assertEqual(storage.open(name).read(), b"zip")


class CheckCloudinaryCommandTests(SimpleTestCase):
    @override_settings(SANAD_CLOUDINARY_ENABLED=False)
    def test_reports_when_cloudinary_is_disabled(self):
        with self.assertRaisesMessage(CommandError, "Cloudinary غير مفعّل"):
            call_command("check_cloudinary")

    @override_settings(SANAD_CLOUDINARY_ENABLED=True)
    @mock.patch("cloudinary.api.ping", return_value={"status": "ok"})
    def test_checks_credentials_without_uploading(self, ping):
        output = StringIO()
        call_command("check_cloudinary", stdout=output)
        ping.assert_called_once_with()
        self.assertIn("يعمل بنجاح", output.getvalue())
