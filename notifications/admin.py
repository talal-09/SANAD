from django.contrib import admin

from .models import ContactAttempt, DeliveryAttempt, MessageTemplate, Notification


class DeliveryAttemptInline(admin.TabularInline):
    model = DeliveryAttempt
    extra = 0
    readonly_fields = ("attempted_at",)
    show_change_link = True


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "message_type", "language", "is_active", "updated_at")
    list_filter = ("message_type", "language", "is_active")
    search_fields = ("name", "body")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "notification_type", "recipient", "channel", "scheduled_at", "status", "priority")
    list_filter = ("notification_type", "channel", "status", "priority", "scheduled_at")
    search_fields = ("patient__patient_number", "patient__full_name", "recipient")
    autocomplete_fields = ("patient", "followup_plan", "appointment", "template", "recipient_user")
    list_select_related = ("patient", "followup_plan", "appointment", "template", "recipient_user")
    readonly_fields = ("created_at",)
    date_hierarchy = "scheduled_at"
    inlines = (DeliveryAttemptInline,)


@admin.register(ContactAttempt)
class ContactAttemptAdmin(admin.ModelAdmin):
    list_display = ("patient", "method", "attempted_at", "result", "coordinator", "next_attempt_at")
    list_filter = ("method", "result", "attempted_at")
    search_fields = ("patient__patient_number", "patient__full_name", "note")
    autocomplete_fields = ("patient", "followup_plan", "coordinator")
    list_select_related = ("patient", "followup_plan", "coordinator")
    readonly_fields = ("created_at",)
    date_hierarchy = "attempted_at"


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("notification", "attempted_at", "was_successful", "provider_reference")
    list_filter = ("was_successful", "attempted_at")
    search_fields = ("notification__recipient", "provider_reference", "failure_reason")
    autocomplete_fields = ("notification",)
    list_select_related = ("notification",)
    readonly_fields = ("attempted_at",)
