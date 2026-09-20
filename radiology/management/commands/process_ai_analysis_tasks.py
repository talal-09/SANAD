from django.core.management.base import BaseCommand, CommandError

from radiology.models import AIAnalysisTask
from radiology.services import (
    AnalysisBackendConfigurationError,
    AnalysisTaskStateError,
    get_analysis_backend,
    run_analysis_task,
)


class Command(BaseCommand):
    help = "تشغيل مهام تحليل دراسات DICOM المنتظرة خارج طلب الويب."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=1,
            help="الحد الأقصى لعدد المهام في التشغيل الواحد.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("يجب أن يكون حد المهام رقمًا موجبًا.")
        try:
            backend = get_analysis_backend()
        except AnalysisBackendConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        task_ids = list(
            AIAnalysisTask.objects.filter(status=AIAnalysisTask.Status.QUEUED)
            .order_by("requested_at")
            .values_list("pk", flat=True)[:limit]
        )
        if not task_ids:
            self.stdout.write("لا توجد مهام تحليل بانتظار التنفيذ.")
            return

        for task_id in task_ids:
            try:
                task = run_analysis_task(task_id, backend=backend)
            except AnalysisTaskStateError as exc:
                self.stderr.write(f"المهمة #{task_id}: {exc}")
                continue
            self.stdout.write(
                f"المهمة #{task.pk}: {task.get_status_display()}"
            )
