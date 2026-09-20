from django.conf import settings
from django.db import models



class Patient(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "ذكر"
        FEMALE = "female", "أنثى"
        UNSPECIFIED = "unspecified", "غير محدد"

    class ContactMethod(models.TextChoices):
        PHONE = "phone", "اتصال هاتفي"
        SMS = "sms", "رسالة نصية"
        EMAIL = "email", "بريد إلكتروني"

    class RecordStatus(models.TextChoices):
        ACTIVE = "active", "نشط"
        INACTIVE = "inactive", "غير نشط"
        DECEASED = "deceased", "متوفى"

    patient_number = models.CharField("رقم المريض", max_length=50, unique=True)
    full_name = models.CharField("الاسم الكامل", max_length=200)
    date_of_birth = models.DateField("تاريخ الميلاد")
    gender = models.CharField("الجنس", max_length=20, choices=Gender.choices)
    phone_number = models.CharField("رقم التواصل", max_length=30)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    city = models.CharField("المدينة", max_length=100, blank=True)
    preferred_contact_method = models.CharField(
        "وسيلة التواصل المفضلة",
        max_length=20,
        choices=ContactMethod.choices,
        default=ContactMethod.PHONE,
    )
    record_status = models.CharField(
        "حالة السجل",
        max_length=20,
        choices=RecordStatus.choices,
        default=RecordStatus.ACTIVE,
        db_index=True,
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_patients",
        verbose_name="سجله",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_patients",
        verbose_name="آخر تعديل بواسطة",
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "مريض"
        verbose_name_plural = "المرضى"
        ordering = ("full_name",)

    def __str__(self):
        return f"{self.full_name} ({self.patient_number})"


class RiskProfile(models.Model):
    class SmokingStatus(models.TextChoices):
        NEVER = "never", "لم يدخن"
        FORMER = "former", "مدخن سابق"
        CURRENT = "current", "مدخن حالي"
        UNKNOWN = "unknown", "غير معروف"

    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="risk_profile",
        verbose_name="المريض",
    )
    smoking_status = models.CharField(
        "حالة التدخين",
        max_length=20,
        choices=SmokingStatus.choices,
        default=SmokingStatus.UNKNOWN,
    )
    smoking_pack_years = models.DecimalField(
        "سنوات العلبة",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    previous_cancer = models.BooleanField("سرطان سابق", default=False)
    family_history = models.BooleanField("تاريخ عائلي", default=False)
    immunosuppressed = models.BooleanField("ضعف المناعة", default=False)
    occupational_exposures = models.TextField("التعرضات المهنية", blank=True)
    related_symptoms = models.TextField("الأعراض ذات العلاقة", blank=True)
    clinician_notes = models.TextField("ملاحظات الطبيب", blank=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "عوامل خطورة"
        verbose_name_plural = "عوامل الخطورة"

    def __str__(self):
        return f"عوامل خطورة: {self.patient}"
