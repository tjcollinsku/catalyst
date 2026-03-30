from django.urls import path

from . import views

urlpatterns = [
    path("api/cases/", views.api_case_collection, name="api_case_collection"),
    path("api/signal-summary/", views.api_signal_summary, name="api_signal_summary"),
    path("api/cases/<uuid:pk>/", views.api_case_detail, name="api_case_detail"),
    path(
        "api/cases/<uuid:pk>/documents/",
        views.api_case_document_collection,
        name="api_case_document_collection",
    ),
    path(
        "api/cases/<uuid:pk>/documents/bulk/",
        views.api_case_document_bulk_upload,
        name="api_case_document_bulk_upload",
    ),
    path(
        "api/cases/<uuid:pk>/documents/process-pending/",
        views.api_case_document_process_pending,
        name="api_case_document_process_pending",
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
    path(
        "api/cases/<uuid:pk>/referrals/",
        views.api_case_referral_collection,
        name="api_case_referral_collection",
    ),
    path(
        "api/cases/<uuid:pk>/referrals/<int:referral_id>/",
        views.api_case_referral_detail,
        name="api_case_referral_detail",
    ),
    path(
        "api/cases/<uuid:pk>/referral-memo/",
        views.api_case_referral_memo,
        name="api_case_referral_memo",
    ),
    path(
        "api/cases/<uuid:pk>/detections/",
        views.api_case_detection_collection,
        name="api_case_detection_collection",
    ),
    path(
        "api/cases/<uuid:pk>/detections/<uuid:detection_id>/",
        views.api_case_detection_detail,
        name="api_case_detection_detail",
    ),
    path("", views.case_list, name="case_list"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:pk>/", views.case_detail, name="case_detail"),
    path("documents/upload/", views.document_upload, name="document_upload"),
]
