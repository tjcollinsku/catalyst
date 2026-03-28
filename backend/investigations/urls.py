from django.urls import path

from . import views

urlpatterns = [
    path("api/cases/", views.api_case_collection, name="api_case_collection"),
    path("api/cases/<uuid:pk>/", views.api_case_detail, name="api_case_detail"),
    path(
        "api/cases/<uuid:pk>/documents/",
        views.api_case_document_collection,
        name="api_case_document_collection",
    ),
    path(
        "api/cases/<uuid:pk>/documents/<uuid:document_id>/",
        views.api_case_document_detail,
        name="api_case_document_detail",
    ),
    path(
        "api/cases/<uuid:pk>/signals/",
        views.api_case_signal_collection,
        name="api_case_signal_collection",
    ),
    path(
        "api/cases/<uuid:pk>/signals/<uuid:signal_id>/",
        views.api_case_signal_detail,
        name="api_case_signal_detail",
    ),
    path("", views.case_list, name="case_list"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:pk>/", views.case_detail, name="case_detail"),
    path("documents/upload/", views.document_upload, name="document_upload"),
]
