from django.urls import path

from . import views

urlpatterns = [
    path("api/csrf/", views.api_csrf_token, name="api_csrf_token"),
    path("api/cases/", views.api_case_collection, name="api_case_collection"),
    path("api/signal-summary/", views.api_signal_summary, name="api_signal_summary"),
    path("api/signals/", views.api_signal_collection, name="api_signal_collection"),
    path("api/referrals/", views.api_referral_collection, name="api_referral_collection"),
    path("api/search/", views.api_search, name="api_search"),
    path("api/entities/", views.api_entity_collection, name="api_entity_collection"),
    path(
        "api/entities/<str:entity_type>/<uuid:entity_id>/",
        views.api_entity_detail,
        name="api_entity_detail",
    ),
    path("api/activity-feed/", views.api_activity_feed, name="api_activity_feed"),
    path("api/cases/<uuid:pk>/", views.api_case_detail, name="api_case_detail"),
    path("api/cases/<uuid:pk>/export/", views.api_case_export, name="api_case_export"),
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
        "api/cases/<uuid:pk>/financials/",
        views.api_case_financials,
        name="api_case_financials",
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
    path(
        "api/cases/<uuid:pk>/findings/",
        views.api_case_finding_collection,
        name="api_case_finding_collection",
    ),
    path(
        "api/cases/<uuid:pk>/findings/<uuid:finding_id>/",
        views.api_case_finding_detail,
        name="api_case_finding_detail",
    ),
    path(
        "api/cases/<uuid:pk>/notes/",
        views.api_case_note_collection,
        name="api_case_note_collection",
    ),
    path(
        "api/cases/<uuid:pk>/notes/<uuid:note_id>/",
        views.api_case_note_detail,
        name="api_case_note_detail",
    ),
    path(
        "api/cases/<uuid:pk>/reevaluate-signals/",
        views.api_case_reevaluate_signals,
        name="api_case_reevaluate_signals",
    ),
    path(
        "api/cases/<uuid:pk>/dashboard/",
        views.api_case_dashboard,
        name="api_case_dashboard",
    ),
    path(
        "api/cases/<uuid:pk>/coverage/",
        views.api_case_coverage,
        name="api_case_coverage",
    ),
    path(
        "api/cases/<uuid:pk>/graph/",
        views.api_case_graph,
        name="api_case_graph",
    ),
    # AI endpoints (Phase 5)
    path(
        "api/cases/<uuid:pk>/ai/summarize/",
        views.api_ai_summarize,
        name="api_ai_summarize",
    ),
    path(
        "api/cases/<uuid:pk>/ai/connections/",
        views.api_ai_connections,
        name="api_ai_connections",
    ),
    path(
        "api/cases/<uuid:pk>/ai/narrative/",
        views.api_ai_narrative,
        name="api_ai_narrative",
    ),
    path(
        "api/cases/<uuid:pk>/ai/ask/",
        views.api_ai_ask,
        name="api_ai_ask",
    ),
    path("", views.case_list, name="case_list"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:pk>/", views.case_detail, name="case_detail"),
    path("documents/upload/", views.document_upload, name="document_upload"),
]
