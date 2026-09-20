from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class HealthcareFacility(models.Model):
    name = models.CharField("اسم المنشأة", max_length=200)
    city = models.CharField("المدينة", max_length=100, blank=True)
    contact_details = models.TextField("بيانات التواصل", blank=True)
    is_active = models.BooleanField("نشطة", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "منشأة صحية"
        verbose_name_plural = "المنشآت الصحية"
        ordering = ("name",)

    def __str__(self):
        return self.name


class PriorityLevel(models.Model):
    name = models.CharField("اسم المستوى", max_length=80, unique=True)
    code = models.SlugField("الرمز", max_length=30, unique=True)
    rank = models.PositiveSmallIntegerField("الترتيب", unique=True)
    response_days = models.PositiveIntegerField("مدة الاستجابة بالأيام", default=7)
    color = models.CharField("اللون", max_length=7, default="#0d766e")
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "مستوى أولوية"
        verbose_name_plural = "مستويات الأولوية"
        ordering = ("rank",)

    def __str__(self):
        return self.name


class SystemSetting(models.Model):
    facility = models.OneToOneField(
        HealthcareFacility,
        on_delete=models.CASCADE,
        related_name="system_settings",
        verbose_name="المنشأة",
    )
    followup_policy = models.TextField("سياسة المتابعة", blank=True)
    escalation_days = models.PositiveIntegerField("مدة التصعيد بالأيام", default=7)
    notification_channels = models.JSONField("قنوات التنبيه", default=list, blank=True)
    priority_settings = models.JSONField("إعدادات الأولوية", default=dict, blank=True)
    upload_settings = models.JSONField("إعدادات رفع الملفات", default=dict, blank=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "إعدادات النظام"
        verbose_name_plural = "إعدادات النظام"

    def __str__(self):
        return f"إعدادات {self.facility}"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="المستخدم",
    )
    action = models.CharField("نوع العملية", max_length=100)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="نوع العنصر",
    )
    object_id = models.CharField("معرف العنصر", max_length=64, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")
    old_values = models.JSONField("القيم القديمة", default=dict, blank=True)
    new_values = models.JSONField("القيم الجديدة", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("عنوان الاتصال", null=True, blank=True)
    created_at = models.DateTimeField("وقت العملية", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "سجل تدقيق"
        verbose_name_plural = "سجلات التدقيق"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("content_type", "object_id"))]

    def __str__(self):
        return f"{self.action} - {self.created_at:%Y-%m-%d %H:%M}"
