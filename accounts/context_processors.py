from django.conf import settings

from .permissions import user_has_capability


def sanad_access(request):
    if not request.user.is_authenticated:
        return {
            "sanad_access": {},
            "allow_public_registration": settings.ALLOW_PUBLIC_REGISTRATION,
        }
    capabilities = (
        "patients.view",
        "patients.register",
        "patients.risk",
        "radiology.view",
        "radiology.manage",
        "followups.view",
        "followups.manage",
        "followups.close",
        "notifications.view",
        "notifications.contact",
    )
    return {
        "allow_public_registration": settings.ALLOW_PUBLIC_REGISTRATION,
        "sanad_access": {
            capability.replace(".", "_"): user_has_capability(
                request.user,
                capability,
            )
            for capability in capabilities
        }
    }
