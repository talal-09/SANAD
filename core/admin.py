from django.contrib import admin

from .models import AuditLog, HealthcareFacility, PriorityLevel, SystemSetting


@admin.register(HealthcareFacility)
class HealthcareFacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "is_active", "updated_at")
    list_filter = ("is_active", "city")
    search_fields = ("name", "city", "contact_details")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PriorityLevel)
class PriorityLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "rank", "response_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("rank",)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("facility", "escalation_days", "updated_at")
    search_fields = ("facility__name",)
    autocomplete_fields = ("facility",)
    readonly_fields = ("updated_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "content_type", "object_id", "created_at")
    list_filter = ("action", "content_type", "created_at")
    search_fields = ("action", "actor__username", "object_id")
    list_select_related = ("actor", "content_type")
    date_hierarchy = "created_at"
    readonly_fields = (
        "actor",
        "action",
        "content_type",
        "object_id",
        "old_values",
        "new_values",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD", "OPTIONS")

    def has_delete_permission(self, request, obj=None):
        return False
