from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDicomStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_DICOM_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Private DICOM files do not have public URLs.")


private_dicom_storage = PrivateDicomStorage()


class PrivateReportStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_REPORT_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Private medical reports do not have public URLs.")


private_report_storage = PrivateReportStorage()
