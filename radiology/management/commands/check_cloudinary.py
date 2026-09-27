from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "تحقق من اتصال Cloudinary دون رفع أي ملفات."

    def handle(self, *args, **options):
        if not settings.SANAD_CLOUDINARY_ENABLED:
            raise CommandError(
                "Cloudinary غير مفعّل. أضف CLOUDINARY_URL ثم أعد تشغيل الأمر."
            )

        try:
            import cloudinary.api

            response = cloudinary.api.ping()
        except Exception as exc:
            raise CommandError(
                "تعذر الاتصال بـ Cloudinary. تحقق من CLOUDINARY_URL والاتصال بالشبكة."
            ) from exc

        if response.get("status") != "ok":
            raise CommandError("أعاد Cloudinary استجابة غير متوقعة.")
        self.stdout.write(self.style.SUCCESS("اتصال Cloudinary يعمل بنجاح."))
