from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, UserProfile
from core.models import HealthcareFacility, PriorityLevel
from followups.models import Appointment, ClosureDecision, FollowUpPlan, Referral, StatusHistory
from notifications.models import ContactAttempt, Notification
from radiology.models import AIAnalysis, ImagingReport, NoduleMeasurement, PulmonaryNodule

from .models import Patient, RiskProfile


settings.SECRET_KEY = "test-only-not-a-production-secret"


class PatientSearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="patient-search-user")
        facility = HealthcareFacility.objects.create(name="منشأة بحث المرضى")
        UserProfile.objects.create(
            user=self.user,
            employee_id="SEARCH-USER-1",
            role=Role.objects.get(code="administrative-staff"),
            facility=facility,
        )
        self.client.force_login(self.user)
        Patient.objects.create(
            registered_by=self.user,
            patient_number="SEARCH-100",
            full_name="أحمد محمد",
            date_of_birth="1980-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0501234567",
        )
        Patient.objects.create(
            registered_by=self.user,
            patient_number="SEARCH-200",
            full_name="سارة علي",
            date_of_birth="1985-01-01",
            gender=Patient.Gender.FEMALE,
            phone_number="0507654321",
        )

    def test_search_filters_by_name_or_patient_number(self):
        response = self.client.get(reverse("patients:index"), {"q": "أحمد"})
        self.assertContains(response, "أحمد محمد")
        self.assertNotContains(response, "سارة علي")

        response = self.client.get(reverse("patients:index"), {"q": "SEARCH-200"})
        self.assertContains(response, "سارة علي")
        self.assertNotContains(response, "أحمد محمد")

    def test_sql_injection_text_is_treated_as_plain_search_text(self):
        response = self.client.get(
            reverse("patients:index"),
            {"q": "' OR 1=1 --"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["patients"]), 0)
        self.assertEqual(Patient.objects.count(), 2)

    def test_patient_text_is_html_escaped(self):
        Patient.objects.create(
            registered_by=self.user,
            patient_number="XSS-300",
            full_name="<script>alert('xss')</script>",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.UNSPECIFIED,
            phone_number="0500000002",
        )

        response = self.client.get(reverse("patients:index"), {"q": "XSS-300"})
        html = response.content.decode()

        self.assertNotIn("<script>alert('xss')</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_user_cannot_list_or_open_patient_from_another_facility(self):
        other_facility = HealthcareFacility.objects.create(name="منشأة أخرى")
        other_user = get_user_model().objects.create_user(username="other-facility-user")
        UserProfile.objects.create(
            user=other_user,
            employee_id="OTHER-FACILITY-1",
            role=Role.objects.get(code="administrative-staff"),
            facility=other_facility,
        )
        hidden_patient = Patient.objects.create(
            registered_by=other_user,
            patient_number="PRIVATE-OTHER-1",
            full_name="مريض منشأة أخرى",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone_number="0500000099",
        )

        listing = self.client.get(reverse("patients:index"))
        detail = self.client.get(reverse("patients:detail", args=(hidden_patient.pk,)))

        self.assertNotContains(listing, hidden_patient.patient_number)
        self.assertEqual(detail.status_code, 404)


class CompleteClinicalWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="clinical-doctor", password="Strong-Test-Password-391!")
        self.facility = HealthcareFacility.objects.create(name="مستشفى مسار الاختبار")
        UserProfile.objects.create(
            user=self.user,
            employee_id="CLINICAL-DOCTOR-1",
            role=Role.objects.get(code="pulmonologist"),
            facility=self.facility,
        )
        self.priority = PriorityLevel.objects.get(code="high")
        self.client.force_login(self.user)

    def test_complete_workflow_from_patient_to_closure_and_notifications(self):
        response = self.client.post(reverse("patients:create"), {
            "patient_number": "P-100", "full_name": "مريض الاختبار", "date_of_birth": "1975-05-12",
            "gender": "male", "phone_number": "0500000000", "email": "", "city": "الرياض",
            "preferred_contact_method": "phone", "record_status": "active",
        })
        patient = Patient.objects.get(patient_number="P-100")
        self.assertRedirects(response, reverse("patients:detail", kwargs={"pk": patient.pk}))

        response = self.client.post(reverse("patients:risk_profile", kwargs={"pk": patient.pk}), {
            "smoking_status": "former", "smoking_pack_years": "20.00", "previous_cancer": "",
            "family_history": "on", "immunosuppressed": "", "occupational_exposures": "",
            "related_symptoms": "", "clinician_notes": "تمت مراجعة عوامل الخطورة.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RiskProfile.objects.filter(patient=patient).exists())

        response = self.client.post(reverse("radiology:create_report"), {
            "patient": patient.pk, "imaging_type": "ct", "performed_at": "2026-09-03T10:00",
            "report_text": "عقدة رئوية تحتاج إلى متابعة.", "indication": "فحص عرضي",
            "facility": self.facility.pk, "original_recommendation": "إعادة التصوير.",
        })
        self.assertEqual(response.status_code, 302)
        report = ImagingReport.objects.get(patient=patient)

        response = self.client.post(reverse("radiology:create_ai_analysis"), {
            "imaging_report": report.pk, "model_name": "test-model", "extracted_data": '{"finding": "nodule"}',
            "confidence_score": "0.9200", "supporting_text": "نص داعم من التقرير.", "review_status": "approved",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AIAnalysis.objects.filter(imaging_report=report, reviewed_by=self.user).exists())

        response = self.client.post(reverse("radiology:create_nodule"), {
            "patient": patient.pk, "nodule_identifier": "N-1", "lung_side": "right", "lobe": "العلوي",
            "location": "محيطية", "nodule_type": "صلبة", "margin": "منتظمة",
            "first_detected_at": "2026-09-03", "status": "active",
        })
        self.assertEqual(response.status_code, 302)
        nodule = PulmonaryNodule.objects.get(patient=patient)

        response = self.client.post(reverse("radiology:create_measurement"), {
            "nodule": nodule.pk, "imaging_report": report.pk, "size_mm": "7.00", "volume_mm3": "",
            "growth_status": "new", "measured_at": "2026-09-03", "clinician_notes": "القياس الأول.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(NoduleMeasurement.objects.filter(nodule=nodule, imaging_report=report).exists())

        response = self.client.post(reverse("followups:create_plan"), {
            "patient": patient.pk, "nodule": nodule.pk, "priority": self.priority.pk,
            "proposed_action": "إعادة الأشعة المقطعية", "start_date": "2026-09-03", "due_date": "2026-12-03",
            "recommendation_source": "تقرير الأشعة", "status": "active",
        })
        self.assertEqual(response.status_code, 302)
        plan = FollowUpPlan.objects.get(patient=patient)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("followups:create_appointment"), {
                "plan": plan.pk, "appointment_type": "أشعة متابعة", "scheduled_at": "2026-12-03T09:00",
                "facility": self.facility.pk, "attendance_status": "scheduled", "change_reason": "",
            })
        self.assertEqual(response.status_code, 302)
        appointment = Appointment.objects.get(plan=plan)

        response = self.client.post(reverse("followups:create_referral"), {
            "plan": plan.pk, "destination": "عيادة الصدرية", "reason": "مراجعة تخصصية",
            "referred_at": "2026-09-04T09:00", "status": "sent",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Referral.objects.filter(plan=plan).exists())

        self.assertTrue(Notification.objects.filter(patient=patient, followup_plan=plan).exists())

        response = self.client.post(reverse("notifications:create_contact_attempt"), {
            "followup_plan": plan.pk, "method": "phone", "attempted_at": "2026-09-05T10:00",
            "result": "reached", "note": "تم تأكيد الموعد.", "next_attempt_at": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ContactAttempt.objects.filter(patient=patient, coordinator=self.user).exists())

        response = self.client.post(reverse("followups:create_closure"), {
            "plan": plan.pk, "outcome": "completed", "reason": "اكتملت المتابعة",
            "closed_at": "2026-12-10T10:00", "clinical_notes": "قرار طبي موثق.",
        })
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.status, FollowUpPlan.Status.CLOSED)
        self.assertTrue(ClosureDecision.objects.filter(plan=plan, closed_by=self.user).exists())
        self.assertTrue(StatusHistory.objects.filter(plan=plan, to_status=FollowUpPlan.Status.CLOSED).exists())
