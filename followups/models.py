from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import models



class FollowUpPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        PENDING_APPROVAL = "pending_approval", "بانتظار الاعتماد"
        ACTIVE = "active", "نشطة"
        OVERDUE = "overdue", "متأخرة"
        COMPLETED = "completed", "مكتملة"
        CLOSED = "closed", "مغلقة"
        CANCELLED = "cancelled", "ملغاة"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="followup_plans",
        verbose_name="المريض",
    )
    nodule = models.ForeignKey(
        "radiology.PulmonaryNodule",
        on_delete=models.PROTECT,
        related_name="followup_plans",
        verbose_name="العقدة الرئوية",
    )
    responsible_clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_followup_plans",
        verbose_name="الطبيب المسؤول",
    )
    priority = models.ForeignKey(
        "core.PriorityLevel",
        on_delete=models.PROTECT,
        related_name="followup_plans",
        verbose_name="مستوى الأولوية",
    )
    proposed_action = models.TextField("الإجراء المقترح")
    start_date = models.DateField("تاريخ بداية الخطة")
    due_date = models.DateField("تاريخ الاستحقاق", db_index=True)
    recommendation_source = models.CharField("مصدر التوصية", max_length=200, blank=True)
    status = models.CharField(
        "حالة الخطة",
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_followup_plans",
        verbose_name="اعتمدها",
    )
    approved_at = models.DateTimeField("تاريخ الاعتماد", null=True, blank=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "خطة متابعة"
        verbose_name_plural = "خطط المتابعة"
        ordering = ("due_date",)
        constraints = [
            models.UniqueConstraint(
                fields=("nodule",),
                condition=Q(status__in=("draft", "pending_approval", "active", "overdue")),
                name="one_open_followup_plan_per_nodule",
            ),
            models.CheckConstraint(
                condition=Q(due_date__gte=models.F("start_date")),
                name="followup_due_date_on_or_after_start",
            ),
        ]

    def __str__(self):
        return f"خطة {self.patient} - {self.due_date}"

    def clean(self):
        super().clean()
        if self.patient_id and self.nodule_id and self.patient_id != self.nodule.patient_id:
            raise ValidationError("يجب أن تنتمي خطة المتابعة والعقدة إلى المريض نفسه.")


class Appointment(models.Model):
    class AttendanceStatus(models.TextChoices):
        SCHEDULED = "scheduled", "مجدول"
        ATTENDED = "attended", "حضر"
        MISSED = "missed", "لم يحضر"
        POSTPONED = "postponed", "مؤجل"
        CANCELLED = "cancelled", "ملغى"

    plan = models.ForeignKey(
        FollowUpPlan,
        on_delete=models.CASCADE,
        related_name="appointments",
        verbose_name="خطة المتابعة",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="المريض",
    )
    appointment_type = models.CharField("نوع الموعد", max_length=100)
    scheduled_at = models.DateTimeField("التاريخ والوقت", db_index=True)
    facility = models.ForeignKey(
        "core.HealthcareFacility",
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="المنشأة أو العيادة",
    )
    attendance_status = models.CharField(
        "حالة الحضور",
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.SCHEDULED,
        db_index=True,
    )
    change_reason = models.TextField("سبب الإلغاء أو التأجيل", blank=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "موعد"
        verbose_name_plural = "المواعيد"
        ordering = ("scheduled_at",)

    def __str__(self):
        return f"{self.patient} - {self.scheduled_at:%Y-%m-%d %H:%M}"

    def clean(self):
        super().clean()
        if self.patient_id and self.plan_id and self.patient_id != self.plan.patient_id:
            raise ValidationError("يجب أن ينتمي الموعد وخطة المتابعة إلى المريض نفسه.")


class Referral(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الإرسال"
        SENT = "sent", "تم الإرسال"
        ACCEPTED = "accepted", "مقبولة"
        COMPLETED = "completed", "مكتملة"
        REJECTED = "rejected", "مرفوضة"

    plan = models.ForeignKey(
        FollowUpPlan,
        on_delete=models.CASCADE,
        related_name="referrals",
        verbose_name="خطة المتابعة",
    )
    destination = models.CharField("الجهة المحال إليها", max_length=200)
    reason = models.TextField("سبب الإحالة")
    referred_at = models.DateTimeField("تاريخ الإحالة")
    status = models.CharField(
        "حالة الإحالة",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    referring_clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_referrals",
        verbose_name="الطبيب المحيل",
    )
    created_at = models.DateTimeField("تاريخ التسجيل", auto_now_add=True)

    class Meta:
        verbose_name = "إحالة"
        verbose_name_plural = "الإحالات"
        ordering = ("-referred_at",)

    def __str__(self):
        return f"إحالة {self.plan_id} إلى {self.destination}"


class StatusHistory(models.Model):
    plan = models.ForeignKey(
        FollowUpPlan,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="خطة المتابعة",
    )
    from_status = models.CharField("الحالة السابقة", max_length=30, blank=True)
    to_status = models.CharField("الحالة الجديدة", max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="followup_status_changes",
        verbose_name="غيّرها",
    )
    note = models.TextField("ملاحظة", blank=True)
    changed_at = models.DateTimeField("وقت التغيير", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "تغير حالة"
        verbose_name_plural = "سجل تغيرات الحالة"
        ordering = ("-changed_at",)

    def __str__(self):
        return f"{self.plan_id}: {self.from_status} ← {self.to_status}"


class ClosureDecision(models.Model):
    class Outcome(models.TextChoices):
        COMPLETED = "completed", "اكتملت المتابعة"
        BENIGN = "benign", "نتيجة حميدة"
        REFERRED = "referred", "تمت الإحالة"
        LOST = "lost", "تعذر استكمال المتابعة"
        OTHER = "other", "أخرى"

    plan = models.OneToOneField(
        FollowUpPlan,
        on_delete=models.PROTECT,
        related_name="closure_decision",
        verbose_name="خطة المتابعة",
    )
    outcome = models.CharField("نتيجة الإغلاق", max_length=20, choices=Outcome.choices)
    reason = models.TextField("سبب الإغلاق")
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="closure_decisions",
        verbose_name="الطبيب الذي أغلق الحالة",
    )
    closed_at = models.DateTimeField("تاريخ الإغلاق", db_index=True)
    clinical_notes = models.TextField("الملاحظات الطبية", blank=True)

    class Meta:
        verbose_name = "قرار إغلاق"
        verbose_name_plural = "قرارات الإغلاق"
        ordering = ("-closed_at",)

    def __str__(self):
        return f"إغلاق الخطة {self.plan_id}: {self.get_outcome_display()}"
