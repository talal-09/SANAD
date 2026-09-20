from django.urls import path

from . import views


app_name = "notifications"

urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.create_notification, name="create"),
    path("contact-attempts/new/", views.create_contact_attempt, name="create_contact_attempt"),
]
