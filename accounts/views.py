import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import Http404

from accounts.permissions import restrict_to_user_facility, user_has_capability
from radiology.models import AIAnalysisTask, AINoduleCandidate
from .forms import MedicalStaffLoginForm, MedicalStaffRegistrationForm


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """عرض بوابة الكادر الطبي."""
    next_step = None
    if user_has_capability(request.user, "radiology.view"):
        candidate = (
            restrict_to_user_facility(
                AINoduleCandidate.objects.filter(
                    analysis_task__status=AIAnalysisTask.Status.COMPLETED,
                    review__isnull=True,
                ),
                request.user,
                patient_path="analysis_task__imaging_study__patient",
            )
            .select_related("analysis_task__imaging_study__patient")
            .order_by("analysis_task__requested_at", "-confidence_score")
            .first()
        )
        if candidate:
            next_step = {
                "label": "راجع النتيجة التالية",
                "description": f"{candidate.analysis_task.imaging_study.patient} — موضع ينتظر قرارك.",
                "url": reverse("radiology:review_nodule_candidate", args=(candidate.pk,)),
                "stage": 4,
            }
        else:
            active_task = (
                restrict_to_user_facility(
                    AIAnalysisTask.objects.filter(
                        status__in=(AIAnalysisTask.Status.QUEUED, AIAnalysisTask.Status.RUNNING)
                    ),
                    request.user,
                    patient_path="imaging_study__patient",
                )
                .select_related("imaging_study__patient")
                .order_by("requested_at")
                .first()
            )
            if active_task:
                next_step = {
                    "label": "تابع التحليل الجاري",
                    "description": f"{active_task.imaging_study.patient} — التحليل يعمل تلقائيًا.",
                    "url": reverse("radiology:study_detail", args=(active_task.imaging_study_id,)),
                    "stage": 3,
                }
            else:
                next_step = {
                    "label": "ابدأ بمريض",
                    "description": "اختر مريضًا موجودًا أو سجّل مريضًا جديدًا ثم ارفع الأشعة.",
                    "url": reverse("patients:index"),
                    "stage": 1,
                }
    elif user_has_capability(request.user, "followups.view"):
        next_step = {
            "label": "راجع المتابعات المستحقة",
            "description": "ابدأ بأقرب خطة أو موعد يحتاج إجراءً.",
            "url": reverse("followups:index"),
            "stage": 5,
        }
    elif user_has_capability(request.user, "patients.view"):
        next_step = {
            "label": "افتح ملفات المرضى",
            "description": "ابحث عن المريض المطلوب للبدء.",
            "url": reverse("patients:index"),
            "stage": 1,
        }
    return render(request, "accounts/index.html", {"next_step": next_step})


def register(request: HttpRequest) -> HttpResponse:
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        raise Http404
    if request.user.is_authenticated:
        return redirect("accounts:index")
    form = MedicalStaffRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "تم إنشاء حسابك وتسجيل الدخول بنجاح.")
        return redirect("accounts:index")
    return render(request, "accounts/register.html", {"form": form})


def sign_in(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("accounts:index")
    username = request.POST.get("username", "").strip().casefold()
    client_ip = request.META.get("REMOTE_ADDR", "unknown")
    fingerprint = hashlib.sha256(f"{client_ip}|{username}".encode()).hexdigest()
    throttle_key = f"sanad:login:{fingerprint}"
    attempts = cache.get(throttle_key, 0) if request.method == "POST" else 0
    if request.method == "POST" and attempts >= settings.LOGIN_MAX_ATTEMPTS:
        form = MedicalStaffLoginForm(request)
        form.cleaned_data = {}
        form.add_error(None, "محاولات دخول كثيرة. انتظر عشر دقائق ثم حاول مرة أخرى.")
        response = render(request, "accounts/login.html", {"form": form}, status=429)
        response["Retry-After"] = str(settings.LOGIN_LOCKOUT_SECONDS)
        return response
    form = MedicalStaffLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        cache.delete(throttle_key)
        login(request, form.get_user())
        messages.success(request, "مرحبًا بعودتك إلى سَنَد.")
        next_url = request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("accounts:index")
    if request.method == "POST":
        if attempts:
            try:
                cache.incr(throttle_key)
            except ValueError:
                cache.set(throttle_key, 1, settings.LOGIN_LOCKOUT_SECONDS)
        else:
            cache.set(throttle_key, 1, settings.LOGIN_LOCKOUT_SECONDS)
    return render(request, "accounts/login.html", {"form": form})


def sign_out(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        logout(request)
    return redirect("core:home")
