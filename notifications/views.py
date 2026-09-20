from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.permissions import capability_required, restrict_to_user_facility

from .forms import ContactAttemptForm
from .models import ContactAttempt, Notification
from .services import run_followup_automation


@login_required
@capability_required("notifications.view")
def index(request: HttpRequest) -> HttpResponse:
    run_followup_automation()
    context = {
        "notifications": restrict_to_user_facility(Notification.objects.select_related("patient", "followup_plan", "appointment"), request.user)[:25],
        "attempts": restrict_to_user_facility(ContactAttempt.objects.select_related("patient", "followup_plan", "coordinator"), request.user)[:20],
    }
    return render(request, "notifications/index.html", context)


def _create(request, form_class, title, success_message, prepare):
    form = form_class(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        prepare(instance)
        instance.full_clean()
        instance.save()
        messages.success(request, success_message)
        return redirect("notifications:index")
    return render(request, "notifications/form.html", {"form": form, "title": title})


@login_required
@capability_required("notifications.view")
def create_notification(request: HttpRequest) -> HttpResponse:
    messages.info(request, "ينشئ سَنَد التنبيهات تلقائيًا من الخطط والمواعيد.")
    return redirect("notifications:index")


@login_required
@capability_required("notifications.contact")
def create_contact_attempt(request: HttpRequest) -> HttpResponse:
    def prepare(attempt):
        attempt.patient = attempt.followup_plan.patient
        attempt.coordinator = request.user
    return _create(request, ContactAttemptForm, "تسجيل محاولة تواصل", "تم تسجيل محاولة التواصل.", prepare)
