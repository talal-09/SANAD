from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import os
import subprocess
import sys
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from core.models import AuditLog

from .models import AIAnalysisTask, AINoduleCandidate


class AnalysisBackendConfigurationError(Exception):
    pass


class AnalysisTaskStateError(Exception):
    pass


@dataclass(frozen=True)
class CandidateResult:
    source_candidate_id: str
    confidence_score: Decimal | float | str
    coordinates: dict
    measurements: dict
    original_output: dict


@dataclass(frozen=True)
class AnalysisResult:
    model_name: str
    model_version: str
    candidates: tuple[CandidateResult, ...]


class AnalysisBackend(Protocol):
    def analyze(self, dicom_zip_path: Path) -> AnalysisResult:
        """حلّل دراسة DICOM حقيقية وأعد الخرج الأصلي للعقد المحتملة."""


def get_analysis_backend() -> AnalysisBackend:
    backend_path = getattr(settings, "SANAD_AI_BACKEND", "").strip()
    if not backend_path:
        raise AnalysisBackendConfigurationError(
            "لم يتم إعداد محرك تحليل حقيقي بعد."
        )
    try:
        backend_class = import_string(backend_path)
        backend = backend_class()
    except (ImportError, AttributeError, TypeError) as exc:
        raise AnalysisBackendConfigurationError(
            "تعذر تحميل محرك التحليل المهيأ."
        ) from exc
    if not callable(getattr(backend, "analyze", None)):
        raise AnalysisBackendConfigurationError(
            "محرك التحليل المهيأ لا يطبق واجهة التحليل المطلوبة."
        )
    return backend


def _record_task_status(task):
    AuditLog.objects.create(
        actor=None,
        action=f"ai_analysis_task.{task.status}",
        content_object=task,
        new_values={"status": task.status},
    )


@transaction.atomic
def _claim_task(task_id):
    task = AIAnalysisTask.objects.select_for_update().select_related(
        "imaging_study"
    ).get(pk=task_id)
    if task.status != AIAnalysisTask.Status.QUEUED:
        raise AnalysisTaskStateError("المهمة ليست بانتظار التنفيذ.")
    if not task.imaging_study.zip_file:
        raise AnalysisTaskStateError("ملف دراسة DICOM غير متوفر للمهمة.")
    task.status = AIAnalysisTask.Status.RUNNING
    task.started_at = timezone.now()
    task.safe_error_message = ""
    task.save(update_fields=("status", "started_at", "safe_error_message"))
    _record_task_status(task)
    return Path(task.imaging_study.zip_file.path)


def _validated_candidates(task, analysis_result):
    if not isinstance(analysis_result, AnalysisResult):
        raise ValidationError("أعاد محرك التحليل نتيجة غير متوافقة.")
    model_name = analysis_result.model_name.strip()
    model_version = analysis_result.model_version.strip()
    if not model_name or len(model_name) > 150:
        raise ValidationError("اسم نموذج التحليل غير صالح.")
    if not model_version or len(model_version) > 80:
        raise ValidationError("إصدار نموذج التحليل غير صالح.")

    candidates = []
    candidate_ids = set()
    for result in analysis_result.candidates:
        if not isinstance(result, CandidateResult):
            raise ValidationError("أعاد محرك التحليل نتيجة عقدة غير متوافقة.")
        candidate_id = result.source_candidate_id.strip()
        if not candidate_id or candidate_id in candidate_ids:
            raise ValidationError("معرف نتيجة النموذج مفقود أو مكرر.")
        candidate_ids.add(candidate_id)
        candidate = AINoduleCandidate(
            analysis_task=task,
            source_candidate_id=candidate_id,
            confidence_score=result.confidence_score,
            coordinates=result.coordinates,
            measurements=result.measurements,
            original_output=result.original_output,
        )
        candidate.full_clean()
        candidates.append(candidate)
    return model_name, model_version, candidates


@transaction.atomic
def _complete_task(task_id, analysis_result):
    task = AIAnalysisTask.objects.select_for_update().get(pk=task_id)
    if task.status != AIAnalysisTask.Status.RUNNING:
        raise AnalysisTaskStateError("تغيرت حالة المهمة أثناء تنفيذ التحليل.")
    model_name, model_version, candidates = _validated_candidates(
        task,
        analysis_result,
    )
    for candidate in candidates:
        candidate.save()
    task.model_name = model_name
    task.model_version = model_version
    task.status = AIAnalysisTask.Status.COMPLETED
    task.finished_at = timezone.now()
    task.safe_error_message = ""
    task.save(
        update_fields=(
            "model_name", "model_version", "status", "finished_at",
            "safe_error_message",
        )
    )
    _record_task_status(task)
    return task


@transaction.atomic
def _fail_task(task_id, safe_message):
    task = AIAnalysisTask.objects.select_for_update().get(pk=task_id)
    if task.status == AIAnalysisTask.Status.RUNNING:
        task.status = AIAnalysisTask.Status.FAILED
        task.finished_at = timezone.now()
        task.safe_error_message = safe_message
        task.save(
            update_fields=("status", "finished_at", "safe_error_message")
        )
        _record_task_status(task)
    return task


def run_analysis_task(task_id, backend=None):
    """شغّل مهمة واحدة خارج طلب الويب واحفظ النتيجة كاملة أو الفشل الآمن."""
    backend = backend or get_analysis_backend()
    dicom_zip_path = _claim_task(task_id)
    try:
        analysis_result = backend.analyze(dicom_zip_path)
        return _complete_task(task_id, analysis_result)
    except AnalysisTaskStateError:
        return AIAnalysisTask.objects.get(pk=task_id)
    except Exception:
        return _fail_task(
            task_id,
            "تعذر إكمال التحليل بواسطة المحرك المهيأ. راجع مسؤول النظام.",
        )


def start_analysis_worker():
    """ابدأ عاملًا محليًا مستقلًا دون إبطاء طلب الويب."""
    if not getattr(settings, "SANAD_AI_AUTOSTART", False):
        return
    command = [
        sys.executable,
        str(Path(settings.BASE_DIR) / "manage.py"),
        "process_ai_analysis_tasks",
        "--limit",
        str(settings.SANAD_AI_WORKER_BATCH_LIMIT),
    ]
    options = {
        "cwd": settings.BASE_DIR,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(command, **options)
