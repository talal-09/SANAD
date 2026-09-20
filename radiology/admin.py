from django.contrib import admin

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


class NoduleMeasurementInline(admin.TabularInline):
    model = NoduleMeasurement
    extra = 0
    autocomplete_fields = ("imaging_report",)
    show_change_link = True


@admin.register(ImagingReport)
class ImagingReportAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "imaging_type", "performed_at", "facility", "review_status")
    list_filter = ("imaging_type", "review_status", "facility", "performed_at")
    search_fields = ("patient__patient_number", "patient__full_name", "report_text")
    autocomplete_fields = ("patient", "facility", "radiologist", "reviewed_by")
    list_select_related = ("patient", "facility", "radiologist", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "performed_at"


@admin.register(PulmonaryNodule)
class PulmonaryNoduleAdmin(admin.ModelAdmin):
    list_display = ("nodule_identifier", "patient", "lung_side", "lobe", "first_detected_at", "status")
    list_filter = ("status", "lung_side", "lobe", "first_detected_at")
    search_fields = ("nodule_identifier", "patient__patient_number", "patient__full_name", "location")
    autocomplete_fields = ("patient",)
    list_select_related = ("patient",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (NoduleMeasurementInline,)


@admin.register(NoduleMeasurement)
class NoduleMeasurementAdmin(admin.ModelAdmin):
    list_display = ("nodule", "imaging_report", "size_mm", "growth_status", "measured_at")
    list_filter = ("growth_status", "measured_at")
    search_fields = ("nodule__nodule_identifier", "nodule__patient__patient_number")
    autocomplete_fields = ("nodule", "imaging_report")
    list_select_related = ("nodule", "imaging_report")
    date_hierarchy = "measured_at"


@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "imaging_report", "model_name", "confidence_score", "review_status", "analyzed_at")
    list_filter = ("review_status", "model_name", "analyzed_at")
    search_fields = ("imaging_report__patient__patient_number", "model_name", "supporting_text")
    autocomplete_fields = ("imaging_report", "reviewed_by")
    list_select_related = ("imaging_report", "reviewed_by")
    readonly_fields = ("analyzed_at",)
    date_hierarchy = "analyzed_at"


@admin.register(ImagingStudy)
class ImagingStudyAdmin(admin.ModelAdmin):
    list_display = (
        "id", "patient", "study_instance_uid", "modality", "study_date",
        "dicom_slice_count", "processing_status", "uploaded_by", "uploaded_at",
    )
    list_filter = ("processing_status", "modality", "study_date", "uploaded_at")
    search_fields = (
        "study_instance_uid", "patient__patient_number", "patient__full_name",
    )
    autocomplete_fields = ("patient", "imaging_report", "uploaded_by")
    list_select_related = ("patient", "imaging_report", "uploaded_by")
    readonly_fields = (
        "study_instance_uid", "modality", "study_date", "dicom_slice_count",
        "processing_status", "error_message", "uploaded_by", "uploaded_at", "updated_at",
    )
    exclude = ("zip_file",)
    date_hierarchy = "uploaded_at"


@admin.register(AIAnalysisTask)
class AIAnalysisTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id", "imaging_study", "status", "model_name", "model_version",
        "requested_by", "requested_at",
    )
    list_filter = ("status", "model_name", "requested_at")
    search_fields = (
        "imaging_study__study_instance_uid",
        "imaging_study__patient__patient_number",
        "model_name",
        "model_version",
    )
    autocomplete_fields = ("imaging_study", "requested_by")
    list_select_related = ("imaging_study", "requested_by")
    readonly_fields = (
        "imaging_study", "status", "model_name", "model_version",
        "safe_error_message", "requested_by", "requested_at", "started_at",
        "finished_at",
    )
    date_hierarchy = "requested_at"

    def has_add_permission(self, request):
        return False


@admin.register(AINoduleCandidate)
class AINoduleCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "source_candidate_id", "analysis_task", "confidence_score", "detected_at",
    )
    list_filter = ("detected_at",)
    search_fields = (
        "source_candidate_id",
        "analysis_task__imaging_study__study_instance_uid",
        "analysis_task__imaging_study__patient__patient_number",
    )
    list_select_related = ("analysis_task", "analysis_task__imaging_study")
    readonly_fields = (
        "analysis_task", "source_candidate_id", "confidence_score", "coordinates",
        "measurements", "original_output", "detected_at",
    )
    date_hierarchy = "detected_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AINoduleCandidateReview)
class AINoduleCandidateReviewAdmin(admin.ModelAdmin):
    list_display = ("candidate", "decision", "reviewed_by", "reviewed_at")
    list_filter = ("decision", "reviewed_at")
    search_fields = (
        "candidate__source_candidate_id",
        "candidate__analysis_task__imaging_study__patient__patient_number",
    )
    list_select_related = (
        "candidate", "candidate__analysis_task", "reviewed_by",
    )
    readonly_fields = (
        "candidate", "decision", "corrected_coordinates", "corrected_measurements",
        "clinician_notes", "reviewed_by", "reviewed_at",
    )
    date_hierarchy = "reviewed_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
