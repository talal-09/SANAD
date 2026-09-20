from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from uuid import uuid4

from .storage import private_dicom_storage, private_report_storage


def imaging_study_upload_path(instance, filename):
    today = timezone.localdate()
    return f"{today:%Y/%m/%d}/{uuid4().hex}.zip"


def imaging_report_upload_path(instance, filename):
    today = timezone.localdate()
    return f"{today:%Y/%m/%d}/{uuid4().hex}.pdf"



class ImagingReport(models.Model):
    class ImagingType(models.TextChoices):
        CT = "ct", "أشعة مقطعية"
        XRAY = "xray", "أشعة سينية"
        PET_CT = "pet_ct", "PET/CT"
        OTHER = "other", "أخرى"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "بانتظار المراجعة"
        REVIEWED = "reviewed", "تمت المراجعة"
        REJECTED = "rejected", "تحتاج تصحيحًا"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="imaging_reports",
        verbose_name="المريض",
    )
    imaging_type = models.CharField("نوع الأشعة", max_length=20, choices=ImagingType.choices)
    performed_at = models.DateTimeField("تاريخ إجراء الأشعة", db_index=True)
    report_text = models.TextField("نص التقرير")
    report_file = models.FileField(
        "ملف التقرير",
        upload_to=imaging_report_upload_path,
        storage=private_report_storage,
        validators=[FileExtensionValidator(("pdf",))],
        blank=True,
    )
    indication = models.TextField("سبب إجراء الأشعة", blank=True)
    facility = models.ForeignKey(
        "core.HealthcareFacility",
        on_delete=models.PROTECT,
        related_name="imaging_reports",
        verbose_name="منشأة الأشعة",
    )
    radiologist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="radiology_reports",
        verbose_name="طبيب الأشعة",
    )
    review_status = models.CharField(
        "حالة المراجعة",
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_imaging_reports",
        verbose_name="راجعه",
    )
    reviewed_at = models.DateTimeField("تاريخ المراجعة", null=True, blank=True)
    original_recommendation = models.TextField("التوصية الأصلية", blank=True)
    created_at = models.DateTimeField("تاريخ الإدخال", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "تقرير أشعة"
        verbose_name_plural = "تقارير الأشعة"
        ordering = ("-performed_at",)

    def __str__(self):
        return f"{self.get_imaging_type_display()} - {self.patient}"


class ImagingStudy(models.Model):
    class ProcessingStatus(models.TextChoices):
        UPLOADED = "uploaded", "مرفوعة"
        VERIFYING = "verifying", "قيد التحقق"
        READY = "ready", "جاهزة"
        FAILED = "failed", "فشلت"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="imaging_studies",
        verbose_name="المريض",
    )
    imaging_report = models.ForeignKey(
        ImagingReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imaging_studies",
        verbose_name="تقرير الأشعة المرتبط",
    )
    zip_file = models.FileField(
        "ملف دراسة DICOM المضغوط",
        upload_to=imaging_study_upload_path,
        storage=private_dicom_storage,
        blank=True,
    )
    study_instance_uid = models.CharField(
        "معرف الدراسة",
        max_length=128,
        blank=True,
        db_index=True,
    )
    modality = models.CharField("نوع الأشعة", max_length=16, blank=True, db_index=True)
    study_date = models.DateField("تاريخ الدراسة", null=True, blank=True, db_index=True)
    dicom_slice_count = models.PositiveIntegerField("عدد شرائح DICOM", default=0)
    processing_status = models.CharField(
        "حالة المعالجة",
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.UPLOADED,
        db_index=True,
    )
    error_message = models.TextField("رسالة الخطأ", blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_imaging_studies",
        verbose_name="رفعها",
    )
    uploaded_at = models.DateTimeField("تاريخ الرفع", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "دراسة أشعة"
        verbose_name_plural = "دراسات الأشعة"
        ordering = ("-uploaded_at",)

    def __str__(self):
        identifier = self.study_instance_uid or f"دراسة {self.pk or 'جديدة'}"
        return f"{identifier} - {self.patient}"

    def clean(self):
        super().clean()
        if (
            self.imaging_report_id
            and self.patient_id
            and self.imaging_report.patient_id != self.patient_id
        ):
            raise ValidationError(
                {"imaging_report": "يجب أن يعود تقرير الأشعة إلى المريض المحدد."}
            )


class AIAnalysisTask(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "بانتظار التنفيذ"
        RUNNING = "running", "قيد التشغيل"
        COMPLETED = "completed", "مكتملة"
        FAILED = "failed", "فاشلة"
        CANCELED = "canceled", "ملغاة"

    imaging_study = models.ForeignKey(
        ImagingStudy,
        on_delete=models.PROTECT,
        related_name="analysis_tasks",
        verbose_name="دراسة الأشعة",
    )
    status = models.CharField(
        "حالة المهمة",
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    model_name = models.CharField("اسم النموذج", max_length=150, blank=True)
    model_version = models.CharField("إصدار النموذج", max_length=80, blank=True)
    safe_error_message = models.TextField("رسالة الخطأ الآمنة", blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_ai_analysis_tasks",
        verbose_name="طلبها",
    )
    requested_at = models.DateTimeField("وقت الطلب", auto_now_add=True, db_index=True)
    started_at = models.DateTimeField("وقت البدء", null=True, blank=True)
    finished_at = models.DateTimeField("وقت الانتهاء", null=True, blank=True)

    class Meta:
        verbose_name = "مهمة تحليل ذكاء اصطناعي"
        verbose_name_plural = "مهام تحليل الذكاء الاصطناعي"
        ordering = ("-requested_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("imaging_study",),
                condition=models.Q(status__in=("queued", "running")),
                name="unique_active_ai_task_per_study",
            )
        ]

    def __str__(self):
        return f"مهمة تحليل {self.pk or 'جديدة'} - {self.get_status_display()}"

    def clean(self):
        super().clean()
        if (
            self.imaging_study_id
            and self.status in (self.Status.QUEUED, self.Status.RUNNING)
            and self.imaging_study.processing_status
            != ImagingStudy.ProcessingStatus.READY
        ):
            raise ValidationError(
                {"imaging_study": "لا يمكن تحليل الدراسة قبل اكتمال التحقق منها."}
            )


class AINoduleCandidate(models.Model):
    analysis_task = models.ForeignKey(
        AIAnalysisTask,
        on_delete=models.PROTECT,
        related_name="nodule_candidates",
        verbose_name="مهمة التحليل",
    )
    source_candidate_id = models.CharField("معرف النتيجة من النموذج", max_length=100)
    confidence_score = models.DecimalField(
        "درجة الثقة الأصلية",
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    coordinates = models.JSONField("الإحداثيات الأصلية", default=dict)
    measurements = models.JSONField("القياسات الأصلية", default=dict)
    original_output = models.JSONField("خرج النموذج الأصلي", default=dict)
    detected_at = models.DateTimeField("وقت تسجيل النتيجة", auto_now_add=True)

    class Meta:
        verbose_name = "عقدة محتملة من التحليل الذكي"
        verbose_name_plural = "العقد المحتملة من التحليل الذكي"
        ordering = ("analysis_task", "source_candidate_id")
        constraints = [
            models.UniqueConstraint(
                fields=("analysis_task", "source_candidate_id"),
                name="unique_ai_candidate_per_task",
            )
        ]

    def __str__(self):
        return f"نتيجة أولية {self.source_candidate_id} - مهمة {self.analysis_task_id}"

    def clean(self):
        super().clean()
        errors = {}
        for field_name in ("coordinates", "measurements", "original_output"):
            if not isinstance(getattr(self, field_name), dict):
                errors[field_name] = "يجب أن تكون البيانات كائن JSON منظمًا."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "analysis_task_id",
                "source_candidate_id",
                "confidence_score",
                "coordinates",
                "measurements",
                "original_output",
            )
            if any(
                getattr(self, field_name) != getattr(original, field_name)
                for field_name in immutable_fields
            ):
                raise ValidationError(
                    "لا يمكن تعديل النتيجة الأصلية للنموذج بعد تسجيلها."
                )
        return super().save(*args, **kwargs)


class AINoduleCandidateReview(models.Model):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "مقبولة"
        CORRECTED = "corrected", "مقبولة بعد التصحيح"
        REJECTED = "rejected", "مرفوضة"

    candidate = models.OneToOneField(
        AINoduleCandidate,
        on_delete=models.PROTECT,
        related_name="review",
        verbose_name="النتيجة المحتملة",
    )
    decision = models.CharField(
        "قرار الطبيب",
        max_length=20,
        choices=Decision.choices,
        db_index=True,
    )
    corrected_coordinates = models.JSONField(
        "الإحداثيات المصححة",
        default=dict,
        blank=True,
    )
    corrected_measurements = models.JSONField(
        "القياسات المصححة",
        default=dict,
        blank=True,
    )
    clinician_notes = models.TextField("ملاحظات الطبيب", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ai_candidate_reviews",
        verbose_name="الطبيب المراجع",
    )
    reviewed_at = models.DateTimeField("وقت المراجعة", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "مراجعة عقدة محتملة"
        verbose_name_plural = "مراجعات العقد المحتملة"
        ordering = ("-reviewed_at",)

    def __str__(self):
        return f"مراجعة {self.candidate_id} - {self.get_decision_display()}"

    def clean(self):
        super().clean()
        errors = {}
        for field_name in ("corrected_coordinates", "corrected_measurements"):
            if not isinstance(getattr(self, field_name), dict):
                errors[field_name] = "يجب أن تكون البيانات كائن JSON منظمًا."
        if self.decision == self.Decision.CORRECTED and not (
            self.corrected_coordinates or self.corrected_measurements
        ):
            errors["decision"] = "أدخل إحداثيات أو قياسات مصححة قبل اعتماد التصحيح."
        if self.decision != self.Decision.CORRECTED:
            if self.corrected_coordinates:
                errors["corrected_coordinates"] = (
                    "تُستخدم الإحداثيات المصححة عند اختيار القبول بعد التصحيح فقط."
                )
            if self.corrected_measurements:
                errors["corrected_measurements"] = (
                    "تُستخدم القياسات المصححة عند اختيار القبول بعد التصحيح فقط."
                )
        if self.decision == self.Decision.REJECTED and not self.clinician_notes.strip():
            errors["clinician_notes"] = "اكتب سبب رفض النتيجة المحتملة."
        if (
            self.candidate_id
            and self.candidate.analysis_task.status != AIAnalysisTask.Status.COMPLETED
        ):
            errors["candidate"] = "لا يمكن مراجعة النتائج قبل اكتمال مهمة التحليل."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "لا يمكن تعديل مراجعة الطبيب بعد تسجيلها؛ يلزم تسجيل تصحيح موثق مستقل."
            )
        return super().save(*args, **kwargs)


class PulmonaryNodule(models.Model):
    class LungSide(models.TextChoices):
        RIGHT = "right", "اليمنى"
        LEFT = "left", "اليسرى"
        UNKNOWN = "unknown", "غير محددة"

    class Status(models.TextChoices):
        ACTIVE = "active", "قيد المتابعة"
        STABLE = "stable", "مستقرة"
        RESOLVED = "resolved", "اختفت"
        CLOSED = "closed", "مغلقة"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="pulmonary_nodules",
        verbose_name="المريض",
    )
    nodule_identifier = models.CharField("معرف العقدة", max_length=50)
    lung_side = models.CharField("جهة الرئة", max_length=20, choices=LungSide.choices)
    lobe = models.CharField("الفص", max_length=50, blank=True)
    location = models.CharField("الموقع", max_length=200, blank=True)
    nodule_type = models.CharField("نوع العقدة", max_length=100, blank=True)
    margin = models.CharField("شكل الحواف", max_length=100, blank=True)
    first_detected_at = models.DateField("تاريخ أول اكتشاف", db_index=True)
    status = models.CharField(
        "حالة العقدة",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "عقدة رئوية"
        verbose_name_plural = "العقد الرئوية"
        ordering = ("patient", "nodule_identifier")
        constraints = [
            models.UniqueConstraint(
                fields=("patient", "nodule_identifier"),
                name="unique_nodule_identifier_per_patient",
            )
        ]

    def __str__(self):
        return f"{self.patient} - عقدة {self.nodule_identifier}"


class NoduleMeasurement(models.Model):
    class GrowthStatus(models.TextChoices):
        NEW = "new", "جديدة"
        STABLE = "stable", "مستقرة"
        INCREASED = "increased", "ازداد الحجم"
        DECREASED = "decreased", "انخفض الحجم"
        UNKNOWN = "unknown", "غير محدد"

    nodule = models.ForeignKey(
        PulmonaryNodule,
        on_delete=models.CASCADE,
        related_name="measurements",
        verbose_name="العقدة",
    )
    imaging_report = models.ForeignKey(
        ImagingReport,
        on_delete=models.PROTECT,
        related_name="nodule_measurements",
        verbose_name="تقرير الأشعة",
    )
    size_mm = models.DecimalField(
        "الحجم بالمليمتر",
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    volume_mm3 = models.DecimalField(
        "الحجم الحجمي (مم³)",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True,
    )
    growth_status = models.CharField(
        "حالة النمو",
        max_length=20,
        choices=GrowthStatus.choices,
        default=GrowthStatus.UNKNOWN,
    )
    measured_at = models.DateField("تاريخ القياس", db_index=True)
    clinician_notes = models.TextField("ملاحظات الطبيب", blank=True)
    created_at = models.DateTimeField("تاريخ التسجيل", auto_now_add=True)

    class Meta:
        verbose_name = "قياس عقدة"
        verbose_name_plural = "قياسات العقد"
        ordering = ("-measured_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("nodule", "imaging_report"),
                name="unique_nodule_measurement_per_report",
            )
        ]

    def __str__(self):
        return f"{self.nodule} - {self.size_mm} مم"

    def clean(self):
        super().clean()
        if (
            self.nodule_id
            and self.imaging_report_id
            and self.nodule.patient_id != self.imaging_report.patient_id
        ):
            raise ValidationError("يجب أن تنتمي العقدة وتقرير الأشعة إلى المريض نفسه.")


class AIAnalysis(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "بانتظار المراجعة"
        APPROVED = "approved", "معتمدة"
        CORRECTED = "corrected", "تم تصحيحها"
        REJECTED = "rejected", "مرفوضة"

    imaging_report = models.ForeignKey(
        ImagingReport,
        on_delete=models.CASCADE,
        related_name="ai_analyses",
        verbose_name="تقرير الأشعة",
    )
    analyzed_at = models.DateTimeField("تاريخ التحليل", auto_now_add=True)
    model_name = models.CharField("النموذج المستخدم", max_length=150)
    extracted_data = models.JSONField("المعلومات المستخرجة", default=dict)
    confidence_score = models.DecimalField(
        "درجة الثقة",
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        null=True,
        blank=True,
    )
    supporting_text = models.TextField("النصوص الداعمة", blank=True)
    review_status = models.CharField(
        "حالة المراجعة",
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_ai_analyses",
        verbose_name="الطبيب المراجع",
    )
    reviewed_at = models.DateTimeField("تاريخ المراجعة", null=True, blank=True)

    class Meta:
        verbose_name = "تحليل ذكاء اصطناعي"
        verbose_name_plural = "تحليلات الذكاء الاصطناعي"
        ordering = ("-analyzed_at",)

    def __str__(self):
        return f"تحليل {self.model_name} - تقرير {self.imaging_report_id}"
