from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import capability_required, restrict_to_user_facility

from .forms import PatientForm, RiskProfileForm
from .models import Patient, RiskProfile


@login_required
@capability_required("patients.view")
def index(request: HttpRequest) -> HttpResponse:
    patients = restrict_to_user_facility(
        Patient.objects.select_related("registered_by"),
        request.user,
        patient_path="",
    ).order_by("full_name")
    query = request.GET.get("q", "").strip()
    if query:
        patients = patients.filter(
            Q(full_name__icontains=query)
            | Q(patient_number__icontains=query)
            | Q(phone_number__icontains=query)
        )
    return render(
        request,
        "patients/index.html",
        {"patients": patients[:50], "query": query},
    )


@login_required
@capability_required("patients.register")
def create(request: HttpRequest) -> HttpResponse:
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save(commit=False)
        patient.registered_by = request.user
        patient.updated_by = request.user
        patient.save()
        messages.success(request, "تم تسجيل المريض بنجاح.")
        return redirect("patients:detail", pk=patient.pk)
    return render(request, "patients/form.html", {"form": form, "title": "تسجيل مريض جديد"})


@login_required
@capability_required("patients.view")
def detail(request: HttpRequest, pk: int) -> HttpResponse:
    patient = get_object_or_404(
        restrict_to_user_facility(Patient.objects.all(), request.user, patient_path=""),
        pk=pk,
    )
    return render(request, "patients/detail.html", {"patient": patient})


@login_required
@capability_required("patients.risk")
def risk_profile(request: HttpRequest, pk: int) -> HttpResponse:
    patient = get_object_or_404(
        restrict_to_user_facility(Patient.objects.all(), request.user, patient_path=""),
        pk=pk,
    )
    profile = RiskProfile.objects.filter(patient=patient).first()
    form = RiskProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.patient = patient
        profile.save()
        messages.success(request, "تم حفظ عوامل الخطورة.")
        return redirect("patients:detail", pk=patient.pk)
    return render(request, "patients/form.html", {"form": form, "title": f"عوامل الخطورة: {patient.full_name}"})
