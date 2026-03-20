from django.urls import path

from . import views

urlpatterns = [
    path("", views.case_list, name="case_list"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:pk>/", views.case_detail, name="case_detail"),
    path("documents/upload/", views.document_upload, name="document_upload"),
]
