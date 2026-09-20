from django.contrib import admin

from .models import Patient, RiskProfile


class RiskProfileInline(admin.StackedInline):
    model = RiskProfile
    extra = 0
    max_num = 1


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("patient_number", "full_name", "date_of_birth", "gender", "city", "record_status")
    list_filter = ("record_status", "gender", "city", "preferred_contact_method")
    search_fields = ("patient_number", "full_name", "phone_number", "email")
    autocomplete_fields = ("registered_by", "updated_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = (RiskProfileInline,)


@admin.register(RiskProfile)
class RiskProfileAdmin(admin.ModelAdmin):
    list_display = ("patient", "smoking_status", "previous_cancer", "family_history", "immunosuppressed")
    list_filter = ("smoking_status", "previous_cancer", "family_history", "immunosuppressed")
    search_fields = ("patient__patient_number", "patient__full_name")
    autocomplete_fields = ("patient",)
    list_select_related = ("patient",)
    readonly_fields = ("updated_at",)
