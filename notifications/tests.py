from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import HealthcareFacility, PriorityLevel
from followups.models import Appointment, FollowUpPlan, StatusHistory
from patients.models import Patient
from radiology.models import PulmonaryNodule

from .models import Notification


settings.SECRET_KEY = "test-only-not-a-production-secret"


class FollowUpAutomationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = get_user_model().objects.create_user("automation-doctor")
        self.facility = HealthcareFacility.objects.create(name="منشأة الأتمتة")
        self.priority = PriorityLevel.objects.get(code="high")
        self.patient = Patient.objects.create(
            patient_number="AUTO-1",
            full_name="مريض الأتمتة",
            date_of_birth="1970-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000000",
            preferred_contact_method=Patient.ContactMethod.SMS,
        )
        self.nodule = PulmonaryNodule.objects.create(
            patient=self.patient,
            nodule_identifier="AUTO-N1",
            lung_side=PulmonaryNodule.LungSide.RIGHT,
            first_detected_at=self.now.date() - timedelta(days=40),
        )
        self.plan = FollowUpPlan.objects.create(
            patient=self.patient,
            nodule=self.nodule,
            responsible_clinician=self.user,
            priority=self.priority,
            proposed_action="متابعة آلية",
            start_date=self.now.date() - timedelta(days=30),
            due_date=self.now.date() - timedelta(days=10),
            status=FollowUpPlan.Status.ACTIVE,
        )
        self.appointment = Appointment.objects.create(
            plan=self.plan,
            patient=self.patient,
            appointment_type="أشعة متابعة",
            scheduled_at=self.now + timedelta(days=14),
            facility=self.facility,
        )

    def test_automation_marks_overdue_escalates_and_schedules_once(self):
        call_command("automate_followups", stdout=StringIO())
        call_command("automate_followups", stdout=StringIO())

        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, FollowUpPlan.Status.OVERDUE)
        self.assertEqual(
            StatusHistory.objects.filter(
                plan=self.plan,
                to_status=FollowUpPlan.Status.OVERDUE,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                followup_plan=self.plan,
                notification_type=Notification.NotificationType.OVERDUE,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                followup_plan=self.plan,
                notification_type=Notification.NotificationType.ESCALATION,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                appointment=self.appointment,
                notification_type=Notification.NotificationType.PATIENT_REMINDER,
            ).count(),
            2,
        )
