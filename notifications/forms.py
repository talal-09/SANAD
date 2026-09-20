from django import forms

from accounts.permissions import restrict_to_user_facility

from .models import ContactAttempt, Notification


class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ("followup_plan", "appointment", "template", "notification_type", "recipient_user", "recipient", "channel", "scheduled_at", "priority")
        widgets = {"scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class ContactAttemptForm(forms.ModelForm):
    class Meta:
        model = ContactAttempt
        fields = ("followup_plan", "method", "attempted_at", "result", "note", "next_attempt_at")
        widgets = {"attempted_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "next_attempt_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["followup_plan"].queryset = restrict_to_user_facility(
                self.fields["followup_plan"].queryset, user
            )
