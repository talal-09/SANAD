from django import forms

from .models import Patient, RiskProfile


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        exclude = ("registered_by", "updated_by")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}


class RiskProfileForm(forms.ModelForm):
    class Meta:
        model = RiskProfile
        exclude = ("patient",)
