from django.contrib import admin

from .models import Role, UserProfile


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "description")
    filter_horizontal = ("permissions",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "role", "facility", "is_active")
    list_filter = ("is_active", "role", "facility")
    search_fields = (
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    autocomplete_fields = ("user", "role", "facility")
    list_select_related = ("user", "role", "facility")
    readonly_fields = ("created_at", "updated_at")
