from functools import wraps

from django.core.exceptions import PermissionDenied


CAPABILITY_ROLES = {
    "patients.view": {
        "radiologist",
        "pulmonologist",
        "followup-coordinator",
        "administrative-staff",
    },
    "patients.register": {
        "radiologist",
        "pulmonologist",
        "administrative-staff",
    },
    "patients.risk": {"radiologist", "pulmonologist"},
    "radiology.view": {"radiologist", "pulmonologist"},
    "radiology.manage": {"radiologist", "pulmonologist"},
    "followups.view": {"pulmonologist", "followup-coordinator"},
    "followups.manage": {"pulmonologist", "followup-coordinator"},
    "followups.close": {"pulmonologist"},
    "notifications.view": {"pulmonologist", "followup-coordinator"},
    "notifications.contact": {"pulmonologist", "followup-coordinator"},
}


def user_has_capability(user, capability):
    """تحقق مركزي من صلاحية المستخدم ودوره النشط."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "sanad_profile", None)
    return bool(
        profile
        and profile.is_active
        and profile.role.is_active
        and profile.role.code in CAPABILITY_ROLES.get(capability, set())
    )


def restrict_to_user_facility(queryset, user, patient_path="patient"):
    """Limit medical records to the facility that owns the patient record."""
    if user.is_superuser:
        return queryset
    profile = getattr(user, "sanad_profile", None)
    if not profile or not profile.is_active:
        return queryset.none()
    prefix = f"{patient_path}__" if patient_path else ""
    lookup = f"{prefix}registered_by__sanad_profile__facility_id"
    return queryset.filter(**{lookup: profile.facility_id})


def capability_required(capability):
    """امنع الوصول إلى الصفحة عندما لا يملك المستخدم الصلاحية المطلوبة."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not user_has_capability(request.user, capability):
                raise PermissionDenied("ليس لديك تصريح لتنفيذ هذه الخطوة.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
