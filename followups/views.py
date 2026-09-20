from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.permissions import capability_required, restrict_to_user_facility
from notifications.services import run_followup_automation

from .forms import AppointmentForm, ClosureDecisionForm, FollowUpPlanForm, ReferralForm
from .models import Appointment, FollowUpPlan, Referral, StatusHistory


@login_required
@capability_required("followups.view")
def index(request: HttpRequest) -> HttpResponse:
    context = {
        "plans": restrict_to_user_facility(FollowUpPlan.objects.select_related("patient", "nodule", "priority", "responsible_clinician"), request.user)[:25],
        "appointments": restrict_to_user_facility(Appointment.objects.select_related("patient", "plan", "facility"), request.user)[:15],
        "referrals": restrict_to_user_facility(Referral.objects.select_related("plan", "referring_clinician"), request.user, patient_path="plan__patient")[:15],
    }
    return render(request, "followups/index.html", context)


def _create(request, form_class, title, success_message, prepare):
    form = form_class(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            instance = form.save(commit=False)
            prepare(instance)
            instance.full_clean()
            instance.save()
        messages.success(request, success_message)
        return redirect("followups:index")
    return render(request, "followups/form.html", {"form": form, "title": title})


@login_required
@capability_required("followups.manage")
def create_plan(request: HttpRequest) -> HttpResponse:
    return _create(request, FollowUpPlanForm, "إنشاء خطة متابعة", "تم إنشاء خطة المتابعة.", lambda plan: setattr(plan, "responsible_clinician", request.user))


@login_required
@capability_required("followups.manage")
def create_appointment(request: HttpRequest) -> HttpResponse:
    def prepare(appointment):
        appointment.patient = appointment.plan.patient
        appointment.facility = request.user.sanad_profile.facility
        transaction.on_commit(run_followup_automation)

    return _create(request, AppointmentForm, "حجز موعد", "تم حفظ الموعد وإنشاء تذكيراته تلقائيًا.", prepare)


@login_required
@capability_required("followups.manage")
def create_referral(request: HttpRequest) -> HttpResponse:
    return _create(request, ReferralForm, "إنشاء إحالة", "تم حفظ الإحالة.", lambda referral: setattr(referral, "referring_clinician", request.user))


@login_required
@capability_required("followups.close")
def create_closure(request: HttpRequest) -> HttpResponse:
    def prepare(decision):
        decision.closed_by = request.user
        previous_status = decision.plan.status
        decision.plan.status = FollowUpPlan.Status.CLOSED
        decision.plan.save(update_fields=("status", "updated_at"))
        StatusHistory.objects.create(plan=decision.plan, from_status=previous_status, to_status=FollowUpPlan.Status.CLOSED, changed_by=request.user, note="أُغلقت الخطة بقرار طبي موثق.")
    return _create(request, ClosureDecisionForm, "توثيق قرار إغلاق", "تم إغلاق الخطة وتوثيق القرار.", prepare)
