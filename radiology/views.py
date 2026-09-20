from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import AuditLog
from accounts.permissions import capability_required, restrict_to_user_facility, user_has_capability

from .ai_backend import (
    preview_pixel_to_physical_point,
    render_candidate_editor_preview,
    render_candidate_preview,
)
from .dicom_validation import DicomStudyValidationError, validate_dicom_zip
from .forms import (
    AIAnalysisForm,
    AINoduleCandidateReviewForm,
    ImagingReportForm,
    ImagingStudyUploadForm,
    NoduleMeasurementForm,
    PulmonaryNoduleForm,
)
from .models import (
    AIAnalysis,
    AIAnalysisTask,
    AINoduleCandidate,
    AINoduleCandidateReview,
    ImagingReport,
    ImagingStudy,
    NoduleMeasurement,
    PulmonaryNodule,
)
from .services import start_analysis_worker


@login_required
@capability_required("radiology.view")
def index(request: HttpRequest) -> HttpResponse:
    experimental_model_path = Path(settings.SANAD_EXPERIMENTAL_AI_MODEL_PATH)
    studies = list(
        restrict_to_user_facility(
            ImagingStudy.objects.select_related("patient", "uploaded_by"), request.user
        )
        .prefetch_related(
            "analysis_tasks__nodule_candidates__review",
        )[:20]
    )
    for study in studies:
        latest_task = next(iter(study.analysis_tasks.all()), None)
        study.result_count = 0
        study.pending_review_count = 0
        if study.processing_status == ImagingStudy.ProcessingStatus.FAILED:
            study.workflow_status = "تعذر تجهيز الدراسة"
            study.workflow_status_code = "failed"
        elif study.processing_status != ImagingStudy.ProcessingStatus.READY:
            study.workflow_status = "جارٍ تجهيز الدراسة"
            study.workflow_status_code = "running"
        elif latest_task is None:
            study.workflow_status = "جاهزة لبدء التحليل"
            study.workflow_status_code = "ready"
        elif latest_task.status in (AIAnalysisTask.Status.QUEUED, AIAnalysisTask.Status.RUNNING):
            study.workflow_status = "التحليل جارٍ"
            study.workflow_status_code = "running"
        elif latest_task.status == AIAnalysisTask.Status.FAILED:
            study.workflow_status = "تعذر إكمال التحليل"
            study.workflow_status_code = "failed"
        elif latest_task.status == AIAnalysisTask.Status.COMPLETED:
            candidates = list(latest_task.nodule_candidates.all())
            study.result_count = len(candidates)
            study.pending_review_count = sum(
                1 for candidate in candidates if not hasattr(candidate, "review")
            )
            if study.pending_review_count:
                study.workflow_status = "تحتاج مراجعة الطبيب"
                study.workflow_status_code = "attention"
            else:
                study.workflow_status = "اكتملت المراجعة"
                study.workflow_status_code = "completed"
        else:
            study.workflow_status = latest_task.get_status_display()
            study.workflow_status_code = latest_task.status
    context = {
        "studies": studies,
        "experimental_model": {
            "available": experimental_model_path.is_file(),
            "name": "MONAI LUNA16 Hard-Negative",
            "version": "عرض تجريبي 1",
            "validation_cases": 88,
            "validation_sensitivity": "96.6%",
            "validation_false_positives_per_scan": "2.03",
            "confidence_threshold": "70%",
        },
    }
    return render(request, "radiology/index.html", context)


def _create(request, form_class, title, success_message, prepare=None):
    form = form_class(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        if prepare:
            prepare(instance)
        instance.full_clean()
        instance.save()
        messages.success(request, success_message)
        return redirect("radiology:index")
    return render(request, "radiology/form.html", {"form": form, "title": title})


@login_required
@capability_required("radiology.manage")
def create_report(request: HttpRequest) -> HttpResponse:
    def prepare(report):
        report.radiologist = request.user
        report.facility = request.user.sanad_profile.facility

    return _create(request, ImagingReportForm, "إضافة تقرير أشعة", "تم حفظ تقرير الأشعة.", prepare)


@login_required
@capability_required("radiology.view")
def download_report(request: HttpRequest, pk: int) -> HttpResponse:
    report = get_object_or_404(
        restrict_to_user_facility(ImagingReport.objects.all(), request.user), pk=pk
    )
    if not report.report_file:
        return HttpResponse(status=404)
    try:
        response = FileResponse(
            report.report_file.open("rb"),
            as_attachment=True,
            filename=f"radiology-report-{report.pk}.pdf",
            content_type="application/pdf",
        )
    except OSError:
        return HttpResponse(status=404)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@capability_required("radiology.manage")
def create_nodule(request: HttpRequest) -> HttpResponse:
    return _create(request, PulmonaryNoduleForm, "تسجيل عقدة رئوية", "تم تسجيل العقدة الرئوية.")


@login_required
@capability_required("radiology.manage")
def create_measurement(request: HttpRequest) -> HttpResponse:
    return _create(request, NoduleMeasurementForm, "إضافة قياس للعقدة", "تم حفظ قياس العقدة.")


@login_required
@capability_required("radiology.manage")
def create_ai_analysis(request: HttpRequest) -> HttpResponse:
    def prepare(analysis):
        if analysis.review_status != AIAnalysis.ReviewStatus.PENDING:
            analysis.reviewed_by = request.user
            analysis.reviewed_at = timezone.now()

    return _create(request, AIAnalysisForm, "تسجيل نتيجة التحليل الذكي", "تم حفظ نتيجة التحليل ومراجعتها.", prepare)


def _can_request_ai_analysis(user):
    return user_has_capability(user, "radiology.manage")


def _can_review_ai_candidate(user):
    return user_has_capability(user, "radiology.manage")


def _record_study_audit(study, actor):
    AuditLog.objects.create(
        actor=actor,
        action=f"imaging_study.{study.processing_status}",
        content_object=study,
        new_values={"processing_status": study.processing_status},
    )


def _queue_analysis_task(study, user):
    with transaction.atomic():
        task = AIAnalysisTask.objects.create(
            imaging_study=study,
            requested_by=user,
        )
        AuditLog.objects.create(
            actor=user,
            action="ai_analysis_task.queued",
            content_object=task,
            new_values={"status": task.status, "imaging_study_id": study.pk},
        )
        transaction.on_commit(start_analysis_worker)
    return task


@login_required
@capability_required("radiology.manage")
def upload_study(request: HttpRequest) -> HttpResponse:
    initial = {}
    patient_id = request.GET.get("patient")
    if patient_id and patient_id.isdigit():
        initial["patient"] = patient_id
    form = ImagingStudyUploadForm(
        request.POST or None, request.FILES or None, initial=initial, user=request.user
    )
    if request.method == "POST" and form.is_valid():
        study = form.save(commit=False)
        study.uploaded_by = request.user
        study.processing_status = ImagingStudy.ProcessingStatus.VERIFYING
        study.save()
        try:
            metadata = validate_dicom_zip(study.zip_file.path)
        except DicomStudyValidationError as exc:
            study.zip_file.delete(save=False)
            study.zip_file = ""
            study.processing_status = ImagingStudy.ProcessingStatus.FAILED
            study.error_message = str(exc)
            study.save(update_fields=("zip_file", "processing_status", "error_message", "updated_at"))
            _record_study_audit(study, request.user)
            messages.error(request, "فشل التحقق من دراسة الأشعة. راجع رسالة الخطأ الآمنة.")
            return redirect("radiology:study_detail", pk=study.pk)

        study.study_instance_uid = metadata.study_instance_uid
        study.modality = metadata.modality
        study.study_date = metadata.study_date
        study.dicom_slice_count = metadata.slice_count
        study.processing_status = ImagingStudy.ProcessingStatus.READY
        study.error_message = ""
        study.save(update_fields=(
            "study_instance_uid", "modality", "study_date", "dicom_slice_count",
            "processing_status", "error_message", "updated_at",
        ))
        _record_study_audit(study, request.user)
        if _can_request_ai_analysis(request.user):
            _queue_analysis_task(study, request.user)
            messages.success(
                request,
                "تم رفع دراسة CT والتحقق منها، وبدأ التحليل الذكي تلقائيًا.",
            )
        else:
            messages.success(request, "تم رفع دراسة CT والتحقق منها بنجاح.")
        return redirect("radiology:study_detail", pk=study.pk)
    return render(
        request,
        "radiology/study_upload.html",
        {"form": form, "max_upload_mb": settings.DICOM_ZIP_MAX_UPLOAD_SIZE // (1024 * 1024)},
    )


@login_required
@capability_required("radiology.view")
def study_detail(request: HttpRequest, pk: int) -> HttpResponse:
    study = get_object_or_404(
        restrict_to_user_facility(
            ImagingStudy.objects.select_related("patient", "imaging_report", "uploaded_by"),
            request.user,
        ),
        pk=pk,
    )
    analysis_tasks = list(
        study.analysis_tasks.select_related("requested_by")
        .prefetch_related("nodule_candidates__review__reviewed_by")[:10]
    )
    active_task = next(
        (
            task
            for task in analysis_tasks
            if task.status in (AIAnalysisTask.Status.QUEUED, AIAnalysisTask.Status.RUNNING)
        ),
        None,
    )
    nodule_candidates = sorted([
        candidate
        for task in analysis_tasks
        for candidate in task.nodule_candidates.all()
    ], key=lambda candidate: candidate.confidence_score, reverse=True)
    for candidate in nodule_candidates:
        candidate.confidence_percent = f"{float(candidate.confidence_score) * 100:.1f}"
        candidate.maximum_dimension_mm = candidate.measurements.get(
            "maximum_dimension_mm"
        )
    return render(
        request,
        "radiology/study_detail.html",
        {
            "study": study,
            "analysis_tasks": analysis_tasks,
            "active_task": active_task,
            "nodule_candidates": nodule_candidates,
            "can_request_ai_analysis": _can_request_ai_analysis(request.user),
            "can_review_ai_candidate": _can_review_ai_candidate(request.user),
        },
    )


@login_required
@capability_required("radiology.manage")
@require_POST
def create_analysis_task(request: HttpRequest, pk: int) -> HttpResponse:
    study = get_object_or_404(
        restrict_to_user_facility(ImagingStudy.objects.all(), request.user), pk=pk
    )
    if study.processing_status != ImagingStudy.ProcessingStatus.READY:
        messages.error(request, "لا يمكن طلب التحليل قبل اكتمال التحقق من الدراسة.")
        return redirect("radiology:study_detail", pk=study.pk)

    try:
        with transaction.atomic():
            _queue_analysis_task(study, request.user)
    except IntegrityError:
        messages.warning(request, "توجد مهمة تحليل نشطة لهذه الدراسة بالفعل.")
    else:
        messages.success(
            request,
            "تم إنشاء مهمة التحليل وهي بانتظار التنفيذ. لم تُنشأ أي نتيجة طبية بعد.",
        )
    return redirect("radiology:study_detail", pk=study.pk)


@login_required
@capability_required("radiology.manage")
def candidate_preview(request: HttpRequest, pk: int) -> HttpResponse:
    candidate = get_object_or_404(
        restrict_to_user_facility(
            AINoduleCandidate.objects.select_related("analysis_task__imaging_study"),
            request.user,
            patient_path="analysis_task__imaging_study__patient",
        ),
        pk=pk,
    )
    study = candidate.analysis_task.imaging_study
    center = candidate.coordinates.get("center")
    diameter = candidate.measurements.get("maximum_dimension_mm")
    if not study.zip_file or not isinstance(center, dict) or diameter is None:
        return HttpResponse(status=404)
    try:
        editor_mode = request.GET.get("editor") == "1"
        if editor_mode:
            image, metadata = render_candidate_editor_preview(
                study.zip_file.path,
                center,
                diameter,
            )
        else:
            image = render_candidate_preview(study.zip_file.path, center, diameter)
            metadata = None
    except (KeyError, OSError, TypeError, ValueError, RuntimeError):
        return HttpResponse("تعذر إنشاء معاينة الأشعة.", status=503)
    response = HttpResponse(image, content_type="image/png")
    if metadata:
        response["X-SANAD-Center-X"] = str(metadata["center_index"]["x"])
        response["X-SANAD-Center-Y"] = str(metadata["center_index"]["y"])
        response["X-SANAD-Image-Width"] = str(metadata["image_size"]["width"])
        response["X-SANAD-Image-Height"] = str(metadata["image_size"]["height"])
        response["X-SANAD-Spacing-X"] = str(metadata["spacing"][0])
        response["X-SANAD-Spacing-Y"] = str(metadata["spacing"][1])
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@capability_required("radiology.manage")
def review_nodule_candidate(request: HttpRequest, pk: int) -> HttpResponse:
    candidate = get_object_or_404(
        restrict_to_user_facility(
            AINoduleCandidate.objects.select_related(
                "analysis_task__imaging_study",
            ),
            request.user,
            patient_path="analysis_task__imaging_study__patient",
        ),
        pk=pk,
    )
    study = candidate.analysis_task.imaging_study
    if hasattr(candidate, "review"):
        messages.warning(request, "تم تسجيل مراجعة طبية لهذه النتيجة بالفعل.")
        return redirect("radiology:study_detail", pk=study.pk)
    if candidate.analysis_task.status != AIAnalysisTask.Status.COMPLETED:
        messages.error(request, "لا يمكن مراجعة النتائج قبل اكتمال مهمة التحليل.")
        return redirect("radiology:study_detail", pk=study.pk)

    review = AINoduleCandidateReview(
        candidate=candidate,
        reviewed_by=request.user,
    )
    form = AINoduleCandidateReviewForm(
        request.POST or None,
        instance=review,
        candidate=candidate,
    )
    if request.method == "POST" and form.is_valid():
        try:
            saved_review = form.save(commit=False)
            if saved_review.decision == AINoduleCandidateReview.Decision.CORRECTED:
                original_center = candidate.coordinates.get("center") or {
                    axis: candidate.coordinates[axis]
                    for axis in ("x", "y", "z")
                }
                original_diameter = (
                    candidate.measurements.get("maximum_dimension_mm")
                    or candidate.measurements["diameter_mm"]
                )
                _image, metadata = render_candidate_editor_preview(
                    study.zip_file.path,
                    original_center,
                    original_diameter,
                )
                saved_review.corrected_coordinates = preview_pixel_to_physical_point(
                    metadata,
                    form.cleaned_data["corrected_center_x"],
                    form.cleaned_data["corrected_center_y"],
                )
                corrected_diameter = float(
                    form.cleaned_data["corrected_diameter_mm"]
                )
                saved_review.corrected_measurements = {
                    "maximum_dimension_mm": corrected_diameter,
                    "method": "manual_axial_diameter",
                }
            saved_review.full_clean()
            with transaction.atomic():
                saved_review.save()
                AuditLog.objects.create(
                    actor=request.user,
                    action=f"ai_candidate_review.{saved_review.decision}",
                    content_object=saved_review,
                    new_values={
                        "candidate_id": candidate.pk,
                        "decision": saved_review.decision,
                    },
                )
        except IntegrityError:
            messages.warning(request, "تم تسجيل مراجعة طبية لهذه النتيجة بالفعل.")
        except (KeyError, OSError, TypeError, ValueError, RuntimeError, ValidationError):
            form.add_error(
                None,
                "تعذر تحويل موضع التصحيح إلى إحداثيات DICOM. أعد فتح الدراسة وحاول مرة أخرى.",
            )
        else:
            messages.success(request, "تم حفظ قرار الطبيب وتوثيقه بنجاح.")
            next_candidate = (
                AINoduleCandidate.objects.filter(
                    analysis_task__imaging_study=study,
                    analysis_task__status=AIAnalysisTask.Status.COMPLETED,
                    review__isnull=True,
                )
                .exclude(pk=candidate.pk)
                .order_by("analysis_task__requested_at", "-confidence_score")
                .first()
            )
            if next_candidate:
                return redirect("radiology:review_nodule_candidate", pk=next_candidate.pk)
            return redirect("radiology:study_detail", pk=study.pk)

    return render(
        request,
        "radiology/candidate_review.html",
        {"candidate": candidate, "form": form, "study": study},
    )
