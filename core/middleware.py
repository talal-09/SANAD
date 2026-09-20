class PrivateMedicalResponseMiddleware:
    """Prevent browsers and shared proxies from caching authenticated PHI pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            getattr(request, "user", None)
            and request.user.is_authenticated
            and "Cache-Control" not in response
        ):
            response["Cache-Control"] = "private, no-store"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
