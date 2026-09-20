from django import forms

from accounts.permissions import restrict_to_user_facility

from .models import Appointment, ClosureDecision, FollowUpPlan, Referral


class FollowUpPlanForm(forms.ModelForm):
    class Meta:
        model = FollowUpPlan
        fields = ("patient", "nodule", "priority", "proposed_action", "start_date", "due_date", "recommendation_source", "status")
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["patient"].queryset = restrict_to_user_facility(
                self.fields["patient"].queryset, user, patient_path=""
            )
            self.fields["nodule"].queryset = restrict_to_user_facility(
                self.fields["nodule"].queryset, user
            )


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("plan", "appointment_type", "scheduled_at", "attendance_status", "change_reason")
        widgets = {"scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["plan"].queryset = restrict_to_user_facility(
                self.fields["plan"].queryset, user
            )


class ReferralForm(forms.ModelForm):
    class Meta:
        model = Referral
        fields = ("plan", "destination", "reason", "referred_at", "status")
        widgets = {"referred_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["plan"].queryset = restrict_to_user_facility(
                self.fields["plan"].queryset, user
            )


class ClosureDecisionForm(forms.ModelForm):
    class Meta:
        model = ClosureDecision
        fields = ("plan", "outcome", "reason", "closed_at", "clinical_notes")
        widgets = {"closed_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["plan"].queryset = restrict_to_user_facility(
                self.fields["plan"].queryset, user
            )
