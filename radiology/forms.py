from django import forms

from django.conf import settings
from accounts.permissions import restrict_to_user_facility

from .models import (
    AIAnalysis,
    AINoduleCandidateReview,
    ImagingReport,
    ImagingStudy,
    NoduleMeasurement,
    PulmonaryNodule,
)


class ImagingReportForm(forms.ModelForm):
    class Meta:
        model = ImagingReport
        fields = ("patient", "imaging_type", "performed_at", "report_text", "report_file", "indication", "original_recommendation")
        widgets = {"performed_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["patient"].queryset = restrict_to_user_facility(
                self.fields["patient"].queryset, user, patient_path=""
            )

    def clean_report_file(self):
        report = self.cleaned_data.get("report_file")
        if not report:
            return report
        if report.size > settings.REPORT_MAX_UPLOAD_SIZE:
            max_mb = settings.REPORT_MAX_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(
                f"حجم التقرير يتجاوز الحد المسموح وهو {max_mb} ميجابايت."
            )
        signature = report.read(5)
        report.seek(0)
        if signature != b"%PDF-":
            raise forms.ValidationError("الملف المرفوع ليس ملف PDF صالحًا.")
        return report


class PulmonaryNoduleForm(forms.ModelForm):
    class Meta:
        model = PulmonaryNodule
        fields = ("patient", "nodule_identifier", "lung_side", "lobe", "location", "nodule_type", "margin", "first_detected_at", "status")
        widgets = {"first_detected_at": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["patient"].queryset = restrict_to_user_facility(
                self.fields["patient"].queryset, user, patient_path=""
            )


class NoduleMeasurementForm(forms.ModelForm):
    class Meta:
        model = NoduleMeasurement
        fields = ("nodule", "imaging_report", "size_mm", "volume_mm3", "growth_status", "measured_at", "clinician_notes")
        widgets = {"measured_at": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["nodule"].queryset = restrict_to_user_facility(
                self.fields["nodule"].queryset, user
            )
            self.fields["imaging_report"].queryset = restrict_to_user_facility(
                self.fields["imaging_report"].queryset, user
            )


class AIAnalysisForm(forms.ModelForm):
    class Meta:
        model = AIAnalysis
        fields = ("imaging_report", "model_name", "extracted_data", "confidence_score", "supporting_text", "review_status")
        widgets = {"extracted_data": forms.Textarea(attrs={"rows": 6, "dir": "ltr"})}
        help_texts = {
            "model_name": "أدخل اسم النموذج كنص عادي، دون تنسيق JSON.",
            "extracted_data": 'أدخل المعلومات بتنسيق JSON صالح، باستخدام علامات اقتباس مزدوجة للمفاتيح والنصوص. مثال بنيوي فقط: {"example": "value"}.',
        }
        error_messages = {
            "extracted_data": {"invalid": "المعلومات المستخرجة: أدخل بيانات JSON صالحة."},
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["imaging_report"].queryset = restrict_to_user_facility(
                self.fields["imaging_report"].queryset, user
            )


class AINoduleCandidateReviewForm(forms.ModelForm):
    corrected_center_x = forms.FloatField(
        required=False,
        widget=forms.HiddenInput,
    )
    corrected_center_y = forms.FloatField(
        required=False,
        widget=forms.HiddenInput,
    )
    corrected_diameter_mm = forms.DecimalField(
        label="القطر المصحح",
        required=False,
        min_value=0.5,
        max_value=100,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={"min": "0.5", "max": "100", "step": "0.1", "inputmode": "decimal"}
        ),
        help_text="اضبط الدائرة حول العقدة؛ يُحفظ القطر بالملليمتر.",
    )

    def __init__(self, *args, **kwargs):
        candidate = kwargs.pop("candidate", None)
        super().__init__(*args, **kwargs)
        self.fields["decision"].choices = [
            choice
            for choice in self.fields["decision"].choices
            if choice[0]
        ]
        if candidate and not self.is_bound:
            original_diameter = (
                candidate.measurements.get("maximum_dimension_mm")
                or candidate.measurements.get("diameter_mm")
            )
            if original_diameter is not None:
                self.fields["corrected_diameter_mm"].initial = round(
                    float(original_diameter),
                    1,
                )

    class Meta:
        model = AINoduleCandidateReview
        fields = (
            "decision",
            "clinician_notes",
        )
        widgets = {
            "decision": forms.RadioSelect,
            "clinician_notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "decision": "اختر قرارًا واحدًا.",
            "clinician_notes": "سبب الرفض إلزامي، ويمكن إضافة ملاحظات لبقية القرارات.",
        }

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["corrected_coordinates"] = (
            cleaned_data.get("corrected_coordinates") or {}
        )
        cleaned_data["corrected_measurements"] = (
            cleaned_data.get("corrected_measurements") or {}
        )
        cleaned_data["clinician_notes"] = (
            cleaned_data.get("clinician_notes") or ""
        ).strip()
        if cleaned_data.get("decision") == AINoduleCandidateReview.Decision.CORRECTED:
            center_x = cleaned_data.get("corrected_center_x")
            center_y = cleaned_data.get("corrected_center_y")
            diameter = cleaned_data.get("corrected_diameter_mm")
            if center_x is None or center_y is None:
                self.add_error(
                    "decision",
                    "حرّك علامة التصحيح إلى مركز العقدة قبل الحفظ.",
                )
            if diameter is None:
                self.add_error(
                    "corrected_diameter_mm",
                    "أدخل القطر المصحح بالملليمتر.",
                )
            if center_x is not None and center_y is not None and diameter is not None:
                self.instance.corrected_coordinates = {
                    "space": "preview_pixel_pending",
                    "x": center_x,
                    "y": center_y,
                }
                self.instance.corrected_measurements = {
                    "maximum_dimension_mm": float(diameter),
                    "method": "manual_axial_diameter",
                }
        else:
            self.instance.corrected_coordinates = {}
            self.instance.corrected_measurements = {}
        return cleaned_data


class ImagingStudyUploadForm(forms.ModelForm):
    zip_file = forms.FileField(
        label="ملف دراسة DICOM المضغوط",
        widget=forms.ClearableFileInput(attrs={"accept": ".zip,application/zip"}),
    )

    class Meta:
        model = ImagingStudy
        fields = ("patient", "imaging_report", "zip_file")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["patient"].queryset = restrict_to_user_facility(
                self.fields["patient"].queryset, user, patient_path=""
            )
            self.fields["imaging_report"].queryset = restrict_to_user_facility(
                self.fields["imaging_report"].queryset, user
            )

    def clean_zip_file(self):
        uploaded_file = self.cleaned_data["zip_file"]
        if uploaded_file.size > settings.DICOM_ZIP_MAX_UPLOAD_SIZE:
            max_mb = settings.DICOM_ZIP_MAX_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"حجم الملف يتجاوز الحد المسموح وهو {max_mb} ميجابايت.")
        return uploaded_file

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        report = cleaned_data.get("imaging_report")
        if patient and report and report.patient_id != patient.pk:
            self.add_error("imaging_report", "يجب أن يعود تقرير الأشعة إلى المريض المحدد.")
        return cleaned_data
