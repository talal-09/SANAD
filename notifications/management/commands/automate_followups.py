from django.core.management.base import BaseCommand

from notifications.services import run_followup_automation


class Command(BaseCommand):
    help = "تحديث المتابعات المتأخرة وجدولة التنبيهات والتصعيدات."

    def handle(self, *args, **options):
        counters = run_followup_automation()
        self.stdout.write(
            self.style.SUCCESS(
                "اكتملت الأتمتة: "
                f"متأخرة={counters['overdue_plans']}، "
                f"تصعيدات={counters['escalations']}، "
                f"تذكيرات={counters['reminders']}"
            )
        )
