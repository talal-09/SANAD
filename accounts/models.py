from django.conf import settings
from django.contrib.auth.models import Permission
from django.db import models



class Role(models.Model):
    name = models.CharField("اسم الدور", max_length=100, unique=True)
    code = models.SlugField("الرمز", max_length=50, unique=True)
    description = models.TextField("الوصف", blank=True)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="sanad_roles",
        verbose_name="الصلاحيات",
    )
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        ordering = ("name",)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sanad_profile",
        verbose_name="المستخدم",
    )
    employee_id = models.CharField("رقم الموظف", max_length=50, unique=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="الدور",
    )
    facility = models.ForeignKey(
        "core.HealthcareFacility",
        on_delete=models.PROTECT,
        related_name="user_profiles",
        verbose_name="المنشأة الصحية",
    )
    phone_number = models.CharField("رقم التواصل", max_length=30, blank=True)
    job_title = models.CharField("المسمى الوظيفي", max_length=100, blank=True)
    is_active = models.BooleanField("الملف نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "ملف مستخدم"
        verbose_name_plural = "ملفات المستخدمين"
        ordering = ("user__first_name", "user__last_name")

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()
