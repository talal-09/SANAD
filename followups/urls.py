from django.urls import path

from . import views


app_name = "followups"

urlpatterns = [
    path("", views.index, name="index"),
    path("plans/new/", views.create_plan, name="create_plan"),
    path("appointments/new/", views.create_appointment, name="create_appointment"),
    path("referrals/new/", views.create_referral, name="create_referral"),
    path("closures/new/", views.create_closure, name="create_closure"),
]
