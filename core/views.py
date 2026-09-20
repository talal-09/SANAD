from django.shortcuts import redirect, render

from django.http import HttpRequest, HttpResponse


def home(request: HttpRequest) -> HttpResponse:
    """عرض الصفحة الرئيسية لنظام سند."""
    if request.user.is_authenticated:
        return redirect("accounts:index")
    return render(request, "core/home.html")
