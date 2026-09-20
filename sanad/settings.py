import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP


BASE_DIR = Path(__file__).resolve().parent.parent


# Keep the existing local signing key; explicit environment configuration wins.
# The local .env uses SECRET_KEY, while Django reads DJANGO_SECRET_KEY.
if not os.environ.get("DJANGO_SECRET_KEY"):
    local_env_path = BASE_DIR / ".env"
    if local_env_path.is_file():
        for local_env_line in local_env_path.read_text(encoding="utf-8-sig").splitlines():
            local_env_name, separator, local_env_value = local_env_line.partition("=")
            if separator and local_env_name.strip() == "SECRET_KEY":
                local_env_value = local_env_value.strip()
                if (len(local_env_value) >= 2 and
                        local_env_value[0] == local_env_value[-1] and
                        local_env_value[0] in ("'", '"')):
                    local_env_value = local_env_value[1:-1]
                if local_env_value:
                    os.environ["DJANGO_SECRET_KEY"] = local_env_value
                break

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")


def env_flag(name, default=False):
    """Read a boolean environment variable without accepting ambiguous values."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_flag("DJANGO_DEBUG", default=True)

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be configured.")
if not DEBUG and (
    SECRET_KEY.startswith("django-insecure-") or len(SECRET_KEY) < 50
):
    raise ImproperlyConfigured(
        "A strong DJANGO_SECRET_KEY of at least 50 characters is required in production."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

# Secure defaults are enabled automatically whenever DEBUG is disabled.
SECURE_SSL_REDIRECT = env_flag("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env_flag("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env_flag("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_HSTS_SECONDS = int(
    os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# Public self-registration is useful for the local prototype only. Production
# administrators create and approve medical accounts through Django Admin.
ALLOW_PUBLIC_REGISTRATION = env_flag(
    "SANAD_ALLOW_PUBLIC_REGISTRATION",
    default=DEBUG,
)
LOGIN_MAX_ATTEMPTS = int(os.environ.get("SANAD_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("SANAD_LOGIN_LOCKOUT_SECONDS", "600"))


INSTALLED_APPS = [
    # تطبيقات Django الأساسية
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "patients.apps.PatientsConfig",
    "radiology.apps.RadiologyConfig",
    "followups.apps.FollowupsConfig",
    "notifications.apps.NotificationsConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.PrivateMedicalResponseMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "sanad.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
                "accounts.context_processors.sanad_access",
            ],
        },
    },
]


WSGI_APPLICATION = "sanad.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


LANGUAGE_CODE = "ar"

TIME_ZONE = "Asia/Riyadh"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"


MEDIA_URL = "media/"

MEDIA_ROOT = BASE_DIR / "media"

# ملفات DICOM حساسة وتبقى خارج مجلد الوسائط العام.
PRIVATE_DICOM_ROOT = BASE_DIR / "private_uploads" / "dicom_studies"
PRIVATE_REPORT_ROOT = BASE_DIR / "private_uploads" / "reports"
PRIVATE_PREVIEW_CACHE_ROOT = BASE_DIR / "private_uploads" / "preview_cache"
PREVIEW_CACHE_MAX_ENTRIES = int(os.environ.get("PREVIEW_CACHE_MAX_ENTRIES", "1000"))
REPORT_MAX_UPLOAD_SIZE = int(
    os.environ.get("REPORT_MAX_UPLOAD_SIZE", 20 * 1024 * 1024)
)
FILE_UPLOAD_PERMISSIONS = 0o600
DICOM_ZIP_MAX_UPLOAD_SIZE = int(
    os.environ.get("DICOM_ZIP_MAX_UPLOAD_SIZE", 100 * 1024 * 1024)
)
DICOM_ZIP_MAX_FILES = int(os.environ.get("DICOM_ZIP_MAX_FILES", 2000))
DICOM_ZIP_MAX_UNCOMPRESSED_SIZE = int(
    os.environ.get("DICOM_ZIP_MAX_UNCOMPRESSED_SIZE", 1024 * 1024 * 1024)
)
DICOM_ZIP_MAX_COMPRESSION_RATIO = int(
    os.environ.get("DICOM_ZIP_MAX_COMPRESSION_RATIO", 200)
)

# محرك MONAI يعمل في بيئة مستقلة حتى لا تختلط اعتماداته مع Django.
SANAD_AI_BACKEND = os.environ.get(
    "SANAD_AI_BACKEND", "radiology.ai_backend.MonaiLungNoduleBackend"
)
SANAD_AI_PYTHON = os.environ.get(
    "SANAD_AI_PYTHON", str(BASE_DIR / ".venv-ai" / "Scripts" / "python.exe")
)
SANAD_AI_MODEL_ROOT = os.environ.get(
    "SANAD_AI_MODEL_ROOT", str(BASE_DIR / "ai_models" / "lung_nodule_ct_detection")
)
SANAD_EXPERIMENTAL_AI_MODEL_PATH = os.environ.get(
    "SANAD_EXPERIMENTAL_AI_MODEL_PATH",
    str(Path(SANAD_AI_MODEL_ROOT) / "models" / "model_experimental_hard_negative.pt"),
)
SANAD_AI_TIMEOUT_SECONDS = int(os.environ.get("SANAD_AI_TIMEOUT_SECONDS", 1800))
SANAD_AI_AUTOSTART = os.environ.get("SANAD_AI_AUTOSTART", "1") == "1"
SANAD_AI_WORKER_BATCH_LIMIT = min(
    max(int(os.environ.get("SANAD_AI_WORKER_BATCH_LIMIT", 25)), 1),
    100,
)


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:index"
LOGOUT_REDIRECT_URL = "core:home"
