import json
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from accounts.models import Role, UserProfile
from core.models import AuditLog, HealthcareFacility
from patients.models import Patient

from .models import (
    AIAnalysisTask,
    AINoduleCandidate,
    AINoduleCandidateReview,
    ImagingReport,
    ImagingStudy,
    PulmonaryNodule,
)
from .forms import ImagingReportForm
from .storage import PrivateDicomStorage


settings.SECRET_KEY = "test-only-not-a-production-secret"


class MedicalReportUploadSecurityTests(TestCase):
    def test_rejects_fake_pdf_content(self):
        form = ImagingReportForm(
            data={},
            files={
                "report_file": SimpleUploadedFile(
                    "report.pdf",
                    b"<script>alert('xss')</script>",
                    content_type="application/pdf",
                )
            },
        )
        form.is_valid()
        self.assertIn("report_file", form.errors)
        self.assertIn("ليس ملف PDF صالحًا", form.errors["report_file"][0])


class ExperimentalModelDisplayTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("experimental-model-viewer")
        facility = HealthcareFacility.objects.create(name="منشأة عرض النموذج")
        UserProfile.objects.create(
            user=self.user,
            employee_id="MODEL-VIEWER-1",
            role=Role.objects.get(code="radiologist"),
            facility=facility,
        )

    @override_settings(SANAD_EXPERIMENTAL_AI_MODEL_PATH=__file__)
    def test_authenticated_user_sees_non_clinical_experimental_model_card(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("radiology:index"))

        self.assertContains(response, "عرض تجريبي فقط")
        self.assertContains(response, "النموذج متصل للعرض")
        self.assertContains(response, "غير مستخدم في التحليل التلقائي")
        self.assertContains(response, "لم يُعتمد للتشخيص")

    def test_radiology_index_focuses_on_studies_without_legacy_sections(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("radiology:index"))

        self.assertContains(response, "الدراسات الأخيرة")
        self.assertContains(response, "معلومات النموذج التجريبي")
        self.assertNotContains(response, "أحدث التقارير")
        self.assertNotContains(response, "العُقَد المعتمدة")

    def test_experimental_model_card_requires_login(self):
        response = self.client.get(reverse("radiology:index"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('radiology:index')}",
        )


class AnalysisWorkerStartupTests(TestCase):
    @override_settings(SANAD_AI_AUTOSTART=True, SANAD_AI_WORKER_BATCH_LIMIT=25)
    @mock.patch("radiology.services.subprocess.Popen")
    def test_worker_is_started_with_a_batch_limit_that_drains_the_queue(self, popen):
        from .services import start_analysis_worker

        start_analysis_worker()

        command = popen.call_args.args[0]
        self.assertEqual(
            command[command.index("--limit") + 1],
            "25",
        )


def synthetic_dicom(study_uid, modality="CT", study_date="20260903"):
    sop_uid = generate_uid()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = CTImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = study_uid
    dataset.Modality = modality
    dataset.StudyDate = study_date
    output = BytesIO()
    dataset.save_as(output, enforce_file_format=True)
    return output.getvalue()


def zip_upload(entries, filename="study.zip"):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return SimpleUploadedFile(filename, output.getvalue(), content_type="application/zip")


@override_settings(SANAD_AI_AUTOSTART=False)
class ImagingStudyUploadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_directory = TemporaryDirectory()
        cls.file_field = ImagingStudy._meta.get_field("zip_file")
        cls.original_storage = cls.file_field.storage
        cls.file_field.storage = PrivateDicomStorage(
            location=cls.private_directory.name,
            base_url=None,
        )

    @classmethod
    def tearDownClass(cls):
        cls.file_field.storage = cls.original_storage
        cls.private_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.facility = HealthcareFacility.objects.create(name="منشأة DICOM التجريبية")
        self.role = Role.objects.get(code="radiologist")
        self.user = get_user_model().objects.create_user(
            username="dicom-doctor",
            password="Strong-Test-Password-391!",
        )
        UserProfile.objects.create(
            user=self.user,
            employee_id="DICOM-1",
            role=self.role,
            facility=self.facility,
        )
        self.patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="DICOM-P1",
            full_name="مريض اصطناعي للاختبار",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.upload_url = reverse("radiology:upload_study")

    def _upload(self, uploaded_file, patient=None, report=None):
        self.client.force_login(self.user)
        data = {
            "patient": (patient or self.patient).pk,
            "imaging_report": report.pk if report else "",
            "zip_file": uploaded_file,
        }
        return self.client.post(self.upload_url, data)

    def test_anonymous_user_cannot_upload(self):
        response = self.client.get(self.upload_url)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.upload_url}",
        )

    def test_authenticated_but_unauthorized_user_cannot_upload(self):
        other_user = get_user_model().objects.create_user("unauthorized-user")
        self.client.force_login(other_user)
        response = self.client.get(self.upload_url)
        self.assertEqual(response.status_code, 403)

    def test_rejects_non_zip_and_preserves_existing_data(self):
        response = self._upload(
            SimpleUploadedFile("not-a-zip.bin", b"not a zip archive")
        )
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertRedirects(response, reverse("radiology:study_detail", args=(study.pk,)))
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("ليس ملف ZIP صالحًا", study.error_message)
        self.assertFalse(study.zip_file)
        self.assertTrue(Patient.objects.filter(pk=self.patient.pk).exists())

    def test_rejects_empty_zip_with_clear_arabic_error(self):
        response = self._upload(zip_upload([]))
        study = ImagingStudy.objects.latest("uploaded_at")
        detail = self.client.get(reverse("radiology:study_detail", args=(study.pk,)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertContains(detail, "ملف ZIP فارغ")

    def test_rejects_zip_slip_path(self):
        uid = generate_uid()
        self._upload(zip_upload((("../escape", synthetic_dicom(uid)),)))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("مسار غير آمن", study.error_message)

    def test_rejects_executable_content(self):
        self._upload(zip_upload((("unsafe.exe", b"synthetic executable"),)))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("محتوى غير مسموح", study.error_message)

    @override_settings(DICOM_ZIP_MAX_FILES=1)
    def test_rejects_archive_over_file_count_limit(self):
        study_uid = generate_uid()
        self._upload(zip_upload((
            ("slice-1", synthetic_dicom(study_uid)),
            ("slice-2", synthetic_dicom(study_uid)),
        )))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("عدد الملفات", study.error_message)

    def test_rejects_non_ct_study(self):
        self._upload(zip_upload((("slice-without-extension", synthetic_dicom(generate_uid(), "MR")),)))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("ليست دراسة أشعة مقطعية CT", study.error_message)

    def test_rejects_slices_from_different_studies(self):
        self._upload(zip_upload((
            ("slice-1", synthetic_dicom(generate_uid())),
            ("nested/slice-2", synthetic_dicom(generate_uid())),
        )))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.FAILED)
        self.assertIn("دراسة DICOM واحدة", study.error_message)

    def test_accepts_valid_ct_zip_and_saves_safe_metadata(self):
        study_uid = generate_uid()
        response = self._upload(zip_upload((
            ("slice-1", synthetic_dicom(study_uid)),
            ("nested/slice-2", synthetic_dicom(study_uid)),
        )))
        study = ImagingStudy.objects.latest("uploaded_at")
        self.assertRedirects(response, reverse("radiology:study_detail", args=(study.pk,)))
        self.assertEqual(study.processing_status, ImagingStudy.ProcessingStatus.READY)
        self.assertEqual(study.study_instance_uid, study_uid)
        self.assertEqual(study.modality, "CT")
        self.assertEqual(study.dicom_slice_count, 2)
        self.assertEqual(str(study.study_date), "2026-09-03")
        audit = AuditLog.objects.get(content_type__model="imagingstudy", object_id=str(study.pk))
        self.assertEqual(audit.new_values, {"processing_status": "ready"})
        self.assertNotIn(self.patient.full_name, str(audit.new_values))
        with self.assertRaises(ValueError):
            study.zip_file.url
        task = AIAnalysisTask.objects.get(imaging_study=study)
        self.assertEqual(task.status, AIAnalysisTask.Status.QUEUED)
        self.assertEqual(task.requested_by, self.user)

    def test_rejects_report_belonging_to_another_patient(self):
        other_patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="DICOM-P2",
            full_name="مريض اصطناعي آخر",
            date_of_birth="1980-01-01",
            gender=Patient.Gender.FEMALE,
            phone_number="0511111111",
        )
        report = ImagingReport.objects.create(
            patient=other_patient,
            imaging_type=ImagingReport.ImagingType.CT,
            performed_at="2026-09-03T10:00:00Z",
            report_text="تقرير اصطناعي.",
            facility=self.facility,
            radiologist=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(self.upload_url, {
            "patient": self.patient.pk,
            "imaging_report": report.pk,
            "zip_file": zip_upload((("slice", synthetic_dicom(generate_uid())),)),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "يجب أن يعود تقرير الأشعة إلى المريض المحدد")
        self.assertFalse(ImagingStudy.objects.exists())


class AIAnalysisFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="analysis-test-doctor")
        facility = HealthcareFacility.objects.create(name="منشأة اصطناعية")
        UserProfile.objects.create(
            user=self.user,
            employee_id="ANALYSIS-TEST-1",
            role=Role.objects.get(code="radiologist"),
            facility=facility,
        )
        patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="AI-TEST-1", full_name="مريض اصطناعي",
            date_of_birth="1970-01-01", gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.report = ImagingReport.objects.create(
            patient=patient, imaging_type=ImagingReport.ImagingType.CT,
            performed_at="2026-09-03T10:00:00Z", report_text="?مريض اصطناعي",
            facility=facility, radiologist=self.user,
        )
        self.data = {
            "imaging_report": self.report.pk, "model_name": "نموذج اختبار v1.0",
            "extracted_data": '{"example": "synthetic"}',
            "confidence_score": "0.8500", "supporting_text": "",
            "review_status": "pending",
        }
        self.url = reverse("radiology:create_ai_analysis")
        self.client.force_login(self.user)

    def test_model_name_is_plain_text_and_only_extracted_data_is_json(self):
        from django import forms
        from .forms import AIAnalysisForm

        form = AIAnalysisForm(data=self.data)
        self.assertIs(type(form.fields["model_name"]), forms.CharField)
        self.assertIsInstance(form.fields["model_name"].widget, forms.TextInput)
        self.assertEqual(form.fields["model_name"].label, "النموذج المستخدم")
        self.assertIsInstance(form.fields["extracted_data"], forms.JSONField)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["model_name"], self.data["model_name"])
        self.assertEqual(form.cleaned_data["extracted_data"], {"example": "synthetic"})

    def test_invalid_json_is_displayed_after_its_own_field_and_not_saved(self):
        from .models import AIAnalysis

        for invalid in ("plain text", "{'example': 'synthetic'}"):
            with self.subTest(invalid=invalid):
                response = self.client.post(self.url, {**self.data, "extracted_data": invalid})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.context["form"].errors), {"extracted_data"})
                html = response.content.decode()
                field_start = html.index('<label for="id_extracted_data">')
                field_end = html.index('</div>', field_start)
                self.assertIn("المعلومات المستخرجة: أدخل بيانات JSON صالحة.", html[field_start:field_end])
                self.assertFalse(AIAnalysis.objects.exists())

    def test_valid_json_and_plain_model_name_are_saved_without_creating_nodule(self):
        from .models import AIAnalysis, PulmonaryNodule

        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse("radiology:index"))
        analysis = AIAnalysis.objects.get()
        self.assertEqual(analysis.model_name, self.data["model_name"])
        self.assertEqual(analysis.extracted_data, {"example": "synthetic"})
        self.assertEqual(analysis.review_status, "pending")
        self.assertIsNone(analysis.reviewed_by)
        self.assertFalse(PulmonaryNodule.objects.exists())


@override_settings(SANAD_AI_AUTOSTART=False)
class AIAnalysisTaskTests(TestCase):
    def setUp(self):
        self.facility = HealthcareFacility.objects.create(name="منشأة مهام التحليل")
        self.role = Role.objects.get(code="radiologist")
        self.user = get_user_model().objects.create_user(
            username="analysis-task-doctor",
            password="Strong-Test-Password-492!",
        )
        UserProfile.objects.create(
            user=self.user,
            employee_id="AI-TASK-1",
            role=self.role,
            facility=self.facility,
        )
        self.patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="AI-TASK-P1",
            full_name="مريض اصطناعي لمهمة التحليل",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.study = ImagingStudy.objects.create(
            patient=self.patient,
            study_instance_uid=generate_uid(),
            modality="CT",
            dicom_slice_count=2,
            processing_status=ImagingStudy.ProcessingStatus.READY,
            uploaded_by=self.user,
        )
        self.url = reverse("radiology:create_analysis_task", args=(self.study.pk,))

    def test_authorized_clinician_can_queue_task_with_audit_record(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("radiology:study_detail", args=(self.study.pk,)),
        )
        task = AIAnalysisTask.objects.get()
        self.assertEqual(task.status, AIAnalysisTask.Status.QUEUED)
        self.assertEqual(task.requested_by, self.user)
        self.assertEqual(task.model_name, "")
        self.assertFalse(PulmonaryNodule.objects.exists())
        audit = AuditLog.objects.get(
            content_type__model="aianalysistask",
            object_id=str(task.pk),
        )
        self.assertEqual(
            audit.new_values,
            {"status": "queued", "imaging_study_id": self.study.pk},
        )

    def test_duplicate_active_task_is_prevented(self):
        AIAnalysisTask.objects.create(
            imaging_study=self.study,
            requested_by=self.user,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AIAnalysisTask.objects.create(
                    imaging_study=self.study,
                    status=AIAnalysisTask.Status.RUNNING,
                    requested_by=self.user,
                )

    def test_terminal_task_allows_a_new_active_task(self):
        AIAnalysisTask.objects.create(
            imaging_study=self.study,
            status=AIAnalysisTask.Status.COMPLETED,
            requested_by=self.user,
        )
        self.client.force_login(self.user)

        self.client.post(self.url)

        self.assertEqual(AIAnalysisTask.objects.count(), 2)
        self.assertEqual(
            AIAnalysisTask.objects.filter(
                status__in=(AIAnalysisTask.Status.QUEUED, AIAnalysisTask.Status.RUNNING)
            ).count(),
            1,
        )

    def test_unverified_study_cannot_be_queued(self):
        self.study.processing_status = ImagingStudy.ProcessingStatus.FAILED
        self.study.save(update_fields=("processing_status", "updated_at"))
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("radiology:study_detail", args=(self.study.pk,)),
        )
        self.assertFalse(AIAnalysisTask.objects.exists())

    def test_unauthorized_user_cannot_queue_task(self):
        unauthorized_user = get_user_model().objects.create_user("analysis-task-unauthorized")
        self.client.force_login(unauthorized_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AIAnalysisTask.objects.exists())

    def test_task_creation_requires_post(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertFalse(AIAnalysisTask.objects.exists())


class AINoduleCandidateTests(TestCase):
    def setUp(self):
        self.facility = HealthcareFacility.objects.create(name="منشأة نتائج التحليل")
        self.role = Role.objects.get(code="radiologist")
        self.user = get_user_model().objects.create_user(
            username="candidate-test-doctor",
            password="Strong-Test-Password-593!",
        )
        UserProfile.objects.create(
            user=self.user,
            employee_id="AI-CANDIDATE-1",
            role=self.role,
            facility=self.facility,
        )
        self.patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="AI-CANDIDATE-P1",
            full_name="مريض اصطناعي لنتيجة التحليل",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.study = ImagingStudy.objects.create(
            patient=self.patient,
            study_instance_uid=generate_uid(),
            modality="CT",
            dicom_slice_count=2,
            processing_status=ImagingStudy.ProcessingStatus.READY,
            uploaded_by=self.user,
        )
        self.task = AIAnalysisTask.objects.create(
            imaging_study=self.study,
            status=AIAnalysisTask.Status.RUNNING,
            model_name="synthetic-test-model",
            model_version="1.0",
            requested_by=self.user,
        )
        self.candidate = AINoduleCandidate.objects.create(
            analysis_task=self.task,
            source_candidate_id="candidate-001",
            confidence_score="0.8500",
            coordinates={"space": "voxel", "x": 10, "y": 20, "z": 30},
            measurements={"diameter_mm": 8.2},
            original_output={"synthetic": True, "score": 0.85},
        )

    def test_original_model_result_is_stored_without_medical_nodule(self):
        self.assertEqual(self.candidate.coordinates["space"], "voxel")
        self.assertEqual(self.candidate.measurements["diameter_mm"], 8.2)
        self.assertEqual(self.candidate.original_output["synthetic"], True)
        self.assertFalse(PulmonaryNodule.objects.exists())

    def test_original_model_result_cannot_be_overwritten(self):
        self.candidate.confidence_score = "0.1000"

        with self.assertRaisesMessage(
            ValidationError,
            "لا يمكن تعديل النتيجة الأصلية للنموذج بعد تسجيلها.",
        ):
            self.candidate.save()

        self.candidate.refresh_from_db()
        self.assertEqual(str(self.candidate.confidence_score), "0.8500")

    def test_candidate_identifier_is_unique_within_task(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AINoduleCandidate.objects.create(
                    analysis_task=self.task,
                    source_candidate_id=self.candidate.source_candidate_id,
                    confidence_score="0.5000",
                    coordinates={},
                    measurements={},
                    original_output={"synthetic": True},
                )

    def test_candidate_page_marks_result_as_preliminary(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("radiology:study_detail", args=(self.study.pk,))
        )

        self.assertContains(response, "مرشحات أولية غير معتمدة طبيًا")
        self.assertContains(response, "موضع محتمل 1")

    def test_candidate_preview_requires_login(self):
        response = self.client.get(
            reverse("radiology:candidate_preview", args=(self.candidate.pk,))
        )
        self.assertEqual(response.status_code, 302)

    @mock.patch("radiology.views.render_candidate_preview", return_value=b"\x89PNG\r\n\x1a\npreview")
    def test_candidate_preview_uses_private_browser_cache(self, _render):
        self.study.zip_file.name = "synthetic-study.zip"
        self.study.save(update_fields=("zip_file",))
        candidate = AINoduleCandidate.objects.create(
            analysis_task=self.task,
            source_candidate_id="candidate-cache-002",
            confidence_score="0.8000",
            coordinates={"center": {"x": 1, "y": 2, "z": 3}},
            measurements={"maximum_dimension_mm": 6.0},
            original_output={"synthetic": True},
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("radiology:candidate_preview", args=(candidate.pk,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, max-age=300")


class AINoduleCandidateReviewTests(TestCase):
    def setUp(self):
        self.facility = HealthcareFacility.objects.create(name="منشأة مراجعة النتائج")
        self.role = Role.objects.get(code="pulmonologist")
        self.user = get_user_model().objects.create_user(
            username="candidate-review-doctor",
            password="Strong-Test-Password-694!",
        )
        UserProfile.objects.create(
            user=self.user,
            employee_id="AI-REVIEW-1",
            role=self.role,
            facility=self.facility,
        )
        self.patient = Patient.objects.create(
            registered_by=self.user,
            patient_number="AI-REVIEW-P1",
            full_name="مريض اصطناعي لمراجعة النتيجة",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.study = ImagingStudy.objects.create(
            patient=self.patient,
            study_instance_uid=generate_uid(),
            modality="CT",
            dicom_slice_count=2,
            processing_status=ImagingStudy.ProcessingStatus.READY,
            uploaded_by=self.user,
        )
        self.task = AIAnalysisTask.objects.create(
            imaging_study=self.study,
            status=AIAnalysisTask.Status.COMPLETED,
            model_name="synthetic-test-model",
            model_version="1.0",
            requested_by=self.user,
        )
        self.candidate = AINoduleCandidate.objects.create(
            analysis_task=self.task,
            source_candidate_id="candidate-review-001",
            confidence_score="0.8500",
            coordinates={"space": "voxel", "x": 10, "y": 20, "z": 30},
            measurements={"diameter_mm": 8.2},
            original_output={"synthetic": True, "score": 0.85},
        )
        self.url = reverse(
            "radiology:review_nodule_candidate",
            args=(self.candidate.pk,),
        )
        self.client.force_login(self.user)

    def test_review_choices_do_not_include_an_empty_english_option(self):
        response = self.client.get(self.url)

        self.assertNotContains(response, "Select an option")
        self.assertContains(response, "مقبولة")

    def test_doctor_can_accept_candidate_without_creating_medical_nodule(self):
        response = self.client.post(
            self.url,
            {
                "decision": AINoduleCandidateReview.Decision.ACCEPTED,
                "corrected_coordinates": "",
                "corrected_measurements": "",
                "clinician_notes": "نتيجة اصطناعية مقبولة للاختبار.",
            },
        )

        self.assertRedirects(
            response,
            reverse("radiology:study_detail", args=(self.study.pk,)),
        )
        review = AINoduleCandidateReview.objects.get()
        self.assertEqual(review.reviewed_by, self.user)
        self.assertEqual(review.decision, AINoduleCandidateReview.Decision.ACCEPTED)
        self.assertFalse(PulmonaryNodule.objects.exists())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.original_output, {"synthetic": True, "score": 0.85})
        audit = AuditLog.objects.get(
            content_type__model="ainodulecandidatereview",
            object_id=str(review.pk),
        )
        self.assertEqual(
            audit.new_values,
            {"candidate_id": self.candidate.pk, "decision": "accepted"},
        )
        self.assertNotIn(review.clinician_notes, str(audit.new_values))

    @mock.patch("radiology.views.render_candidate_editor_preview")
    def test_doctor_can_store_correction_separately_from_original_result(self, render_preview):
        self.study.zip_file.name = "synthetic/review-study.zip"
        self.study.save(update_fields=("zip_file", "updated_at"))
        render_preview.return_value = (
            b"synthetic-preview",
            {
                "center_index": {"x": 10, "y": 20, "z": 30},
                "image_size": {"width": 100, "height": 100, "depth": 60},
                "origin": [0, 0, 0],
                "spacing": [1, 1, 1],
                "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1],
            },
        )
        response = self.client.post(
            self.url,
            {
                "decision": AINoduleCandidateReview.Decision.CORRECTED,
                "corrected_center_x": "11",
                "corrected_center_y": "20",
                "corrected_diameter_mm": "7.8",
                "clinician_notes": "تصحيح اصطناعي للاختبار.",
            },
        )

        self.assertEqual(response.status_code, 302)
        review = AINoduleCandidateReview.objects.get()
        self.assertEqual(review.corrected_coordinates["center"]["x"], 11)
        self.assertEqual(review.corrected_coordinates["center"]["z"], 30)
        self.assertEqual(review.corrected_measurements["maximum_dimension_mm"], 7.8)
        self.assertEqual(self.candidate.coordinates["x"], 10)
        self.assertEqual(self.candidate.measurements["diameter_mm"], 8.2)

    def test_correction_screen_uses_visual_tool_instead_of_json_fields(self):
        response = self.client.get(self.url)

        self.assertContains(response, "اسحب الدائرة إلى مركز العقدة")
        self.assertContains(response, "القطر المصحح")
        self.assertNotContains(response, "الإحداثيات المصححة")
        self.assertNotContains(response, "القياسات المصححة")
        self.assertContains(response, "prepareEditorPreview")
        self.assertContains(response, "await decodeImage(loadedObjectUrl)")
        self.assertContains(response, 'image.src = editorObjectUrl')

    def test_rejection_requires_clinician_reason(self):
        response = self.client.post(
            self.url,
            {
                "decision": AINoduleCandidateReview.Decision.REJECTED,
                "corrected_coordinates": "",
                "corrected_measurements": "",
                "clinician_notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("clinician_notes", response.context["form"].errors)
        self.assertFalse(AINoduleCandidateReview.objects.exists())

    def test_candidate_cannot_be_reviewed_before_task_completion(self):
        self.task.status = AIAnalysisTask.Status.RUNNING
        self.task.save(update_fields=("status",))

        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            reverse("radiology:study_detail", args=(self.study.pk,)),
        )
        self.assertFalse(AINoduleCandidateReview.objects.exists())

    def test_unauthorized_user_cannot_review_candidate(self):
        unauthorized_user = get_user_model().objects.create_user("review-unauthorized")
        self.client.force_login(unauthorized_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AINoduleCandidateReview.objects.exists())

    def test_saved_review_cannot_be_silently_changed(self):
        review = AINoduleCandidateReview.objects.create(
            candidate=self.candidate,
            decision=AINoduleCandidateReview.Decision.ACCEPTED,
            reviewed_by=self.user,
        )
        review.decision = AINoduleCandidateReview.Decision.REJECTED

        with self.assertRaisesMessage(
            ValidationError,
            "لا يمكن تعديل مراجعة الطبيب بعد تسجيلها",
        ):
            review.save()


class SuccessfulTestAnalysisBackend:
    def analyze(self, dicom_zip_path):
        from .services import AnalysisResult, CandidateResult

        if not dicom_zip_path.is_file():
            raise RuntimeError("ملف الاختبار غير موجود")
        return AnalysisResult(
            model_name="synthetic-test-backend",
            model_version="1.0",
            candidates=(
                CandidateResult(
                    source_candidate_id="backend-candidate-001",
                    confidence_score="0.9100",
                    coordinates={"space": "voxel", "x": 10, "y": 20, "z": 30},
                    measurements={"diameter_mm": 8.4},
                    original_output={"synthetic_test_result": True, "score": 0.91},
                ),
            ),
        )


class FailingTestAnalysisBackend:
    def analyze(self, dicom_zip_path):
        raise RuntimeError("تفصيل تقني حساس لا يجب عرضه")


class InvalidTestAnalysisBackend:
    def analyze(self, dicom_zip_path):
        return {"invalid": "result"}


class AIAnalysisExecutionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_directory = TemporaryDirectory()
        cls.file_field = ImagingStudy._meta.get_field("zip_file")
        cls.original_storage = cls.file_field.storage
        cls.file_field.storage = PrivateDicomStorage(
            location=cls.private_directory.name,
            base_url=None,
        )

    @classmethod
    def tearDownClass(cls):
        cls.file_field.storage = cls.original_storage
        cls.private_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user("analysis-execution-user")
        self.patient = Patient.objects.create(
            patient_number="AI-EXECUTION-P1",
            full_name="مريض اصطناعي لتنفيذ التحليل",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
        )
        self.study = ImagingStudy.objects.create(
            patient=self.patient,
            zip_file=SimpleUploadedFile("study.zip", b"synthetic test archive"),
            study_instance_uid=generate_uid(),
            modality="CT",
            dicom_slice_count=2,
            processing_status=ImagingStudy.ProcessingStatus.READY,
            uploaded_by=self.user,
        )
        self.task = AIAnalysisTask.objects.create(
            imaging_study=self.study,
            requested_by=self.user,
        )

    @override_settings(
        SANAD_AI_BACKEND="radiology.tests.SuccessfulTestAnalysisBackend"
    )
    def test_command_completes_task_and_persists_original_results(self):
        call_command("process_ai_analysis_tasks", stdout=StringIO())

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, AIAnalysisTask.Status.COMPLETED)
        self.assertEqual(self.task.model_name, "synthetic-test-backend")
        self.assertEqual(self.task.model_version, "1.0")
        candidate = AINoduleCandidate.objects.get(analysis_task=self.task)
        self.assertEqual(str(candidate.confidence_score), "0.9100")
        self.assertEqual(candidate.original_output["synthetic_test_result"], True)
        self.assertFalse(PulmonaryNodule.objects.exists())
        self.assertTrue(
            AuditLog.objects.filter(
                content_type__model="aianalysistask",
                object_id=str(self.task.pk),
                action="ai_analysis_task.running",
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                content_type__model="aianalysistask",
                object_id=str(self.task.pk),
                action="ai_analysis_task.completed",
            ).exists()
        )

    @override_settings(SANAD_AI_BACKEND="radiology.tests.FailingTestAnalysisBackend")
    def test_backend_failure_is_saved_without_exposing_technical_details(self):
        from .services import run_analysis_task

        run_analysis_task(self.task.pk)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, AIAnalysisTask.Status.FAILED)
        self.assertIn("تعذر إكمال التحليل", self.task.safe_error_message)
        self.assertNotIn("تفصيل تقني حساس", self.task.safe_error_message)
        self.assertFalse(AINoduleCandidate.objects.exists())

    @override_settings(SANAD_AI_BACKEND="radiology.tests.InvalidTestAnalysisBackend")
    def test_invalid_backend_output_fails_atomically(self):
        from .services import run_analysis_task

        run_analysis_task(self.task.pk)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, AIAnalysisTask.Status.FAILED)
        self.assertFalse(AINoduleCandidate.objects.exists())

    @override_settings(SANAD_AI_BACKEND="")
    def test_missing_backend_configuration_leaves_task_queued(self):
        with self.assertRaisesMessage(
            CommandError,
            "لم يتم إعداد محرك تحليل حقيقي بعد.",
        ):
            call_command("process_ai_analysis_tasks", stdout=StringIO())

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, AIAnalysisTask.Status.QUEUED)


class MonaiLungNoduleBackendTests(TestCase):
    @override_settings(
        SANAD_AI_PYTHON=__file__,
        SANAD_AI_MODEL_ROOT=Path(__file__).parent,
        SANAD_AI_TIMEOUT_SECONDS=30,
    )
    @mock.patch("radiology.ai_backend.subprocess.run")
    @mock.patch("radiology.ai_backend.Path.is_file", return_value=True)
    def test_backend_converts_worker_json_without_changing_original_output(
        self, _is_file, run
    ):
        from .ai_backend import MonaiLungNoduleBackend

        worker_output = {
            "candidates": [
                {
                    "score": 0.87504,
                    "coordinates": {
                        "space": "world_mm_from_monai_bundle",
                        "box_mode": "cccwhd",
                        "center": {"x": 1.0, "y": 2.0, "z": 3.0},
                    },
                    "measurements": {
                        "width_mm": 4.0,
                        "height_mm": 5.0,
                        "depth_mm": 6.0,
                        "maximum_dimension_mm": 6.0,
                    },
                    "original_output": {
                        "box": [1, 2, 3, 4, 5, 6],
                        "box_mode": "cccwhd",
                        "label": 0,
                        "score": 0.87504,
                    },
                }
            ]
        }
        run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps(worker_output),
        )

        result = MonaiLungNoduleBackend().analyze(Path("study.zip"))

        self.assertEqual(result.model_version, "0.6.9")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.source_candidate_id, "monai-0001")
        self.assertEqual(candidate.confidence_score, Decimal("0.8750"))
        self.assertEqual(candidate.original_output, worker_output["candidates"][0]["original_output"])
        self.assertNotIn("patient", run.call_args.kwargs)

    def test_worker_rejects_inconsistent_result_lengths(self):
        from .ai_worker import _candidate_payload

        with self.assertRaisesMessage(ValueError, "inconsistent MONAI result"):
            _candidate_payload(
                {"box": [[1, 2, 3, 4, 5, 6]], "label": [0], "label_scores": []}
            )

    @override_settings(SANAD_AI_PYTHON=__file__)
    @mock.patch("radiology.ai_backend.subprocess.run")
    @mock.patch("radiology.ai_backend.Path.is_file", return_value=True)
    def test_preview_accepts_only_png_output(self, _is_file, run):
        from .ai_backend import render_candidate_preview

        def create_preview(command, **_options):
            output_path = Path(command[command.index("--preview-output") + 1])
            metadata_path = Path(command[command.index("--preview-metadata-output") + 1])
            output_path.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
            metadata_path.write_text(
                json.dumps({
                    "center_index": {"x": 1, "y": 2, "z": 3},
                    "image_size": {"width": 10, "height": 10, "depth": 10},
                    "origin": [0, 0, 0],
                    "spacing": [1, 1, 1],
                    "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                }),
                encoding="utf-8",
            )
            return mock.Mock(returncode=0)

        run.side_effect = create_preview
        with TemporaryDirectory() as cache_directory, override_settings(
            PRIVATE_PREVIEW_CACHE_ROOT=cache_directory,
            PREVIEW_CACHE_MAX_ENTRIES=10,
        ):
            result = render_candidate_preview(
                Path("synthetic-study.zip"),
                {"x": 1, "y": 2, "z": 3},
                6.0,
            )
            cached_result = render_candidate_preview(
                Path("synthetic-study.zip"),
                {"x": 1, "y": 2, "z": 3},
                6.0,
            )
        self.assertTrue(result.startswith(b"\x89PNG"))
        self.assertEqual(cached_result, result)
        self.assertEqual(run.call_count, 1)

    def test_preview_pixel_is_converted_to_dicom_physical_point(self):
        from .ai_backend import preview_pixel_to_physical_point

        result = preview_pixel_to_physical_point(
            {
                "center_index": {"x": 5, "y": 6, "z": 4},
                "image_size": {"width": 20, "height": 20, "depth": 10},
                "origin": [10, 20, 30],
                "spacing": [0.5, 0.75, 2],
                "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1],
            },
            8,
            12,
        )

        self.assertEqual(result["center"], {"x": 14.0, "y": 29.0, "z": 38.0})
