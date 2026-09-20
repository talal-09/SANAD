from django.urls import path

from . import views


app_name = "patients"

urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/risk-profile/", views.risk_profile, name="risk_profile"),
]
