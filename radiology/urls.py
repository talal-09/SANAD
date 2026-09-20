from django.urls import path

from . import views


app_name = "radiology"

urlpatterns = [
    path("", views.index, name="index"),
    path("reports/new/", views.create_report, name="create_report"),
    path("reports/<int:pk>/download/", views.download_report, name="download_report"),
    path("nodules/new/", views.create_nodule, name="create_nodule"),
    path("measurements/new/", views.create_measurement, name="create_measurement"),
    path("ai-analyses/new/", views.create_ai_analysis, name="create_ai_analysis"),
    path("studies/upload/", views.upload_study, name="upload_study"),
    path("studies/<int:pk>/", views.study_detail, name="study_detail"),
    path(
        "studies/<int:pk>/analysis-tasks/new/",
        views.create_analysis_task,
        name="create_analysis_task",
    ),
    path(
        "ai-candidates/<int:pk>/review/",
        views.review_nodule_candidate,
        name="review_nodule_candidate",
    ),
    path(
        "ai-candidates/<int:pk>/preview/",
        views.candidate_preview,
        name="candidate_preview",
    ),
]
