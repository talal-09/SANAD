from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from followups.models import Appointment, FollowUpPlan, StatusHistory

from .models import Notification


def _patient_recipient(patient):
    if patient.preferred_contact_method == patient.ContactMethod.EMAIL and patient.email:
        return patient.email, Notification.Channel.EMAIL
    if patient.preferred_contact_method == patient.ContactMethod.SMS:
        return patient.phone_number, Notification.Channel.SMS
    return patient.phone_number, Notification.Channel.PHONE


@transaction.atomic
def run_followup_automation(now=None):
    """حدّث المتابعات وأنشئ التنبيهات المستحقة دون تكرار."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    counters = {"overdue_plans": 0, "escalations": 0, "reminders": 0}

    overdue_plans = FollowUpPlan.objects.select_related(
        "patient", "responsible_clinician"
    ).filter(
        status__in=(FollowUpPlan.Status.ACTIVE, FollowUpPlan.Status.PENDING_APPROVAL),
        due_date__lt=today,
    )
    for plan in overdue_plans:
        previous_status = plan.status
        plan.status = FollowUpPlan.Status.OVERDUE
        plan.save(update_fields=("status", "updated_at"))
        StatusHistory.objects.create(
            plan=plan,
            from_status=previous_status,
            to_status=FollowUpPlan.Status.OVERDUE,
            note="غيّر النظام الحالة تلقائيًا بعد تجاوز تاريخ الاستحقاق.",
        )
        _, created = Notification.objects.get_or_create(
            followup_plan=plan,
            appointment=None,
            notification_type=Notification.NotificationType.OVERDUE,
            defaults={
                "patient": plan.patient,
                "recipient_user": plan.responsible_clinician,
                "recipient": plan.responsible_clinician.get_username(),
                "channel": Notification.Channel.IN_APP,
                "scheduled_at": now,
                "priority": Notification.Priority.HIGH,
            },
        )
        counters["overdue_plans"] += int(created)

    escalated_plans = FollowUpPlan.objects.select_related(
        "patient", "priority", "responsible_clinician"
    ).filter(status=FollowUpPlan.Status.OVERDUE)
    for plan in escalated_plans:
        escalation_date = plan.due_date + timedelta(days=plan.priority.response_days)
        if today < escalation_date:
            continue
        _, created = Notification.objects.get_or_create(
            followup_plan=plan,
            appointment=None,
            notification_type=Notification.NotificationType.ESCALATION,
            defaults={
                "patient": plan.patient,
                "recipient_user": plan.responsible_clinician,
                "recipient": plan.responsible_clinician.get_username(),
                "channel": Notification.Channel.IN_APP,
                "scheduled_at": now,
                "priority": Notification.Priority.URGENT,
            },
        )
        counters["escalations"] += int(created)

    upcoming_appointments = Appointment.objects.select_related(
        "patient", "plan"
    ).filter(
        attendance_status=Appointment.AttendanceStatus.SCHEDULED,
        scheduled_at__gt=now,
        scheduled_at__lte=now + timedelta(days=90),
    )
    for appointment in upcoming_appointments:
        recipient, channel = _patient_recipient(appointment.patient)
        for days_before in (7, 1):
            reminder_at = appointment.scheduled_at - timedelta(days=days_before)
            _, created = Notification.objects.get_or_create(
                followup_plan=appointment.plan,
                appointment=appointment,
                notification_type=Notification.NotificationType.PATIENT_REMINDER,
                channel=channel,
                scheduled_at=reminder_at,
                defaults={
                    "patient": appointment.patient,
                    "recipient": recipient,
                    "priority": Notification.Priority.NORMAL,
                },
            )
            counters["reminders"] += int(created)

    return counters
