from django.contrib import admin

from .models import Appointment, ClosureDecision, FollowUpPlan, Referral, StatusHistory


class AppointmentInline(admin.TabularInline):
    model = Appointment
    extra = 0
    autocomplete_fields = ("patient", "facility")
    show_change_link = True


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    readonly_fields = ("changed_at",)
    autocomplete_fields = ("changed_by",)
    show_change_link = True


@admin.register(FollowUpPlan)
class FollowUpPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "nodule", "responsible_clinician", "priority", "due_date", "status")
    list_filter = ("status", "priority", "due_date", "start_date")
    search_fields = ("patient__patient_number", "patient__full_name", "nodule__nodule_identifier")
    autocomplete_fields = ("patient", "nodule", "responsible_clinician", "priority", "approved_by")
    list_select_related = ("patient", "nodule", "responsible_clinician", "priority")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "due_date"
    inlines = (AppointmentInline, StatusHistoryInline)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "appointment_type", "scheduled_at", "facility", "attendance_status")
    list_filter = ("attendance_status", "appointment_type", "facility", "scheduled_at")
    search_fields = ("patient__patient_number", "patient__full_name")
    autocomplete_fields = ("plan", "patient", "facility")
    list_select_related = ("plan", "patient", "facility")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "scheduled_at"


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("plan", "destination", "referred_at", "status", "referring_clinician")
    list_filter = ("status", "referred_at")
    search_fields = ("destination", "plan__patient__patient_number", "plan__patient__full_name")
    autocomplete_fields = ("plan", "referring_clinician")
    list_select_related = ("plan", "referring_clinician")
    date_hierarchy = "referred_at"


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("plan", "from_status", "to_status", "changed_by", "changed_at")
    list_filter = ("to_status", "changed_at")
    search_fields = ("plan__patient__patient_number", "plan__patient__full_name", "note")
    autocomplete_fields = ("plan", "changed_by")
    list_select_related = ("plan", "changed_by")
    readonly_fields = ("changed_at",)
    date_hierarchy = "changed_at"


@admin.register(ClosureDecision)
class ClosureDecisionAdmin(admin.ModelAdmin):
    list_display = ("plan", "outcome", "closed_by", "closed_at")
    list_filter = ("outcome", "closed_at")
    search_fields = ("plan__patient__patient_number", "plan__patient__full_name", "reason")
    autocomplete_fields = ("plan", "closed_by")
    list_select_related = ("plan", "closed_by")
    date_hierarchy = "closed_at"
