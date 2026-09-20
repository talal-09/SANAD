from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models



class MessageTemplate(models.Model):
    class MessageType(models.TextChoices):
        APPOINTMENT = "appointment", "موعد"
        REMINDER = "reminder", "تذكير"
        ESCALATION = "escalation", "تصعيد"
        GENERAL = "general", "عام"

    name = models.CharField("اسم القالب", max_length=150, unique=True)
    message_type = models.CharField("نوع الرسالة", max_length=20, choices=MessageType.choices)
    body = models.TextField("نص الرسالة العام والآمن")
    language = models.CharField("اللغة", max_length=10, default="ar")
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "قالب رسالة"
        verbose_name_plural = "قوالب الرسائل"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        TEAM_ALERT = "team_alert", "تنبيه للفريق"
        PATIENT_REMINDER = "patient_reminder", "تذكير للمريض"
        OVERDUE = "overdue", "تأخر متابعة"
        ESCALATION = "escalation", "تصعيد"

    class Channel(models.TextChoices):
        IN_APP = "in_app", "داخل النظام"
        SMS = "sms", "رسالة نصية"
        EMAIL = "email", "بريد إلكتروني"
        PHONE = "phone", "اتصال هاتفي"

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        SENT = "sent", "تم الإرسال"
        DELIVERED = "delivered", "تم التسليم"
        FAILED = "failed", "فشل"
        CANCELLED = "cancelled", "ملغى"

    class Priority(models.TextChoices):
        LOW = "low", "منخفضة"
        NORMAL = "normal", "عادية"
        HIGH = "high", "عالية"
        URGENT = "urgent", "عاجلة"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="notifications",
        verbose_name="المريض",
    )
    followup_plan = models.ForeignKey(
        "followups.FollowUpPlan",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="خطة المتابعة",
    )
    appointment = models.ForeignKey(
        "followups.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="الموعد",
    )
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="قالب الرسالة",
    )
    notification_type = models.CharField("نوع التنبيه", max_length=30, choices=NotificationType.choices)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sanad_notifications",
        verbose_name="المستخدم المستلم",
    )
    recipient = models.CharField("المستلم", max_length=255)
    channel = models.CharField("قناة الإرسال", max_length=20, choices=Channel.choices)
    scheduled_at = models.DateTimeField("وقت الإرسال", db_index=True)
    sent_at = models.DateTimeField("وقت الإرسال الفعلي", null=True, blank=True)
    status = models.CharField(
        "حالة الإرسال",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    priority = models.CharField(
        "درجة الأولوية",
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    class Meta:
        verbose_name = "تنبيه"
        verbose_name_plural = "التنبيهات"
        ordering = ("scheduled_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("followup_plan", "notification_type"),
                condition=models.Q(
                    appointment__isnull=True,
                    notification_type__in=("overdue", "escalation"),
                ),
                name="unique_plan_automation_alert",
            ),
            models.UniqueConstraint(
                fields=(
                    "appointment",
                    "notification_type",
                    "channel",
                    "scheduled_at",
                ),
                condition=models.Q(appointment__isnull=False),
                name="unique_appointment_reminder",
            ),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.recipient}"

    def clean(self):
        super().clean()
        errors = {}
        if self.patient_id and self.followup_plan_id and self.patient_id != self.followup_plan.patient_id:
            errors["patient"] = "يجب أن ينتمي التنبيه وخطة المتابعة إلى المريض نفسه."
        if self.appointment_id and self.followup_plan_id and self.appointment.plan_id != self.followup_plan_id:
            errors["appointment"] = "يجب أن ينتمي الموعد إلى خطة المتابعة المحددة."
        if errors:
            raise ValidationError(errors)


class ContactAttempt(models.Model):
    class Method(models.TextChoices):
        PHONE = "phone", "اتصال هاتفي"
        SMS = "sms", "رسالة نصية"
        EMAIL = "email", "بريد إلكتروني"
        OTHER = "other", "أخرى"

    class Result(models.TextChoices):
        REACHED = "reached", "تم التواصل"
        NO_ANSWER = "no_answer", "لا يوجد رد"
        INVALID_CONTACT = "invalid_contact", "بيانات التواصل غير صحيحة"
        RESCHEDULED = "rescheduled", "أعيدت الجدولة"
        OTHER = "other", "أخرى"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="contact_attempts",
        verbose_name="المريض",
    )
    followup_plan = models.ForeignKey(
        "followups.FollowUpPlan",
        on_delete=models.CASCADE,
        related_name="contact_attempts",
        verbose_name="خطة المتابعة",
    )
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contact_attempts",
        verbose_name="منسق المتابعة",
    )
    method = models.CharField("وسيلة التواصل", max_length=20, choices=Method.choices)
    attempted_at = models.DateTimeField("تاريخ المحاولة", db_index=True)
    result = models.CharField("نتيجة المحاولة", max_length=30, choices=Result.choices)
    note = models.TextField("الملاحظة", blank=True)
    next_attempt_at = models.DateTimeField("موعد المحاولة التالية", null=True, blank=True)
    created_at = models.DateTimeField("تاريخ التسجيل", auto_now_add=True)

    class Meta:
        verbose_name = "محاولة تواصل"
        verbose_name_plural = "محاولات التواصل"
        ordering = ("-attempted_at",)

    def __str__(self):
        return f"{self.patient} - {self.get_result_display()}"

    def clean(self):
        super().clean()
        if self.patient_id and self.followup_plan_id and self.patient_id != self.followup_plan.patient_id:
            raise ValidationError("يجب أن تنتمي محاولة التواصل وخطة المتابعة إلى المريض نفسه.")


class DeliveryAttempt(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
        verbose_name="التنبيه",
    )
    attempted_at = models.DateTimeField("وقت المحاولة", auto_now_add=True, db_index=True)
    was_successful = models.BooleanField("نجحت المحاولة", default=False)
    provider_reference = models.CharField("مرجع مزود الخدمة", max_length=255, blank=True)
    failure_reason = models.TextField("سبب الفشل", blank=True)

    class Meta:
        verbose_name = "محاولة إرسال"
        verbose_name_plural = "سجل محاولات الإرسال"
        ordering = ("-attempted_at",)

    def __str__(self):
        return f"محاولة إرسال للتنبيه {self.notification_id}"
