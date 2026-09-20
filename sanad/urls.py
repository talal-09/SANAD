from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    # الصفحة الرئيسية
    path("", include("core.urls")),

    # لوحة إدارة Django
    path("admin/", admin.site.urls),

    # تطبيقات سند
    path("accounts/", include("accounts.urls")),
    path("patients/", include("patients.urls")),
    path("radiology/", include("radiology.urls")),
    path("followups/", include("followups.urls")),
    path("notifications/", include("notifications.urls")),
]


# عرض الملفات المرفوعة أثناء التطوير المحلي فقط
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )