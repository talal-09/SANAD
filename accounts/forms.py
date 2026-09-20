from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from core.models import HealthcareFacility

from .models import Role, UserProfile


class MedicalStaffLoginForm(AuthenticationForm):
    username = forms.CharField(label="اسم المستخدم")
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput)


class MedicalStaffRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="الاسم الأول", max_length=150)
    last_name = forms.CharField(label="اسم العائلة", max_length=150)
    email = forms.EmailField(label="البريد الإلكتروني")
    employee_id = forms.CharField(label="رقم الموظف", max_length=50)
    role = forms.ModelChoiceField(label="الدور الوظيفي", queryset=Role.objects.none())
    facility = forms.ModelChoiceField(label="المنشأة الصحية", queryset=HealthcareFacility.objects.none())
    phone_number = forms.CharField(label="رقم التواصل", max_length=30, required=False)
    job_title = forms.CharField(label="المسمى الوظيفي", max_length=100, required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(is_active=True).exclude(code="system-admin")
        self.fields["facility"].queryset = HealthcareFacility.objects.filter(is_active=True)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("يوجد حساب مسجل بهذا البريد الإلكتروني.")
        return email

    def clean_employee_id(self):
        employee_id = self.cleaned_data["employee_id"].strip()
        if UserProfile.objects.filter(employee_id__iexact=employee_id).exists():
            raise forms.ValidationError("رقم الموظف مستخدم مسبقًا.")
        return employee_id

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                employee_id=self.cleaned_data["employee_id"],
                role=self.cleaned_data["role"],
                facility=self.cleaned_data["facility"],
                phone_number=self.cleaned_data["phone_number"],
                job_title=self.cleaned_data["job_title"],
            )
        return user
