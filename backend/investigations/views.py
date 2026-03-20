import hashlib
import os

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CaseForm, DocumentUploadForm
from .models import Case, Document


def case_list(request):
    cases = Case.objects.order_by("-created_at")
    return render(request, "investigations/case_list.html", {"cases": cases})


def case_create(request):
    if request.method == "POST":
        form = CaseForm(request.POST)
        if form.is_valid():
            case = form.save()
            return redirect("case_detail", pk=case.pk)
    else:
        form = CaseForm()
    return render(request, "investigations/case_form.html", {"form": form, "title": "New Case"})


def case_detail(request, pk):
    case = get_object_or_404(Case, pk=pk)
    documents = case.documents.order_by("-uploaded_at")
    return render(request, "investigations/case_detail.html", {"case": case, "documents": documents})


def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES["file"]
            case = form.cleaned_data["case"]

            # Compute SHA-256 of the uploaded file
            sha = hashlib.sha256()
            for chunk in uploaded.chunks():
                sha.update(chunk)
            sha256 = sha.hexdigest()

            # Build storage path: media/cases/<case_id>/<filename>
            relative_path = f"cases/{case.pk}/{uploaded.name}"
            from django.core.files.storage import default_storage
            saved_path = default_storage.save(relative_path, uploaded)

            Document.objects.create(
                case=case,
                filename=uploaded.name,
                file_path=saved_path,
                sha256_hash=sha256,
                file_size=uploaded.size,
                doc_type=form.cleaned_data["doc_type"],
                source_url=form.cleaned_data.get("source_url") or None,
                uploaded_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return redirect("case_detail", pk=case.pk)
    else:
        case_pk = request.GET.get("case")
        initial = {"case": case_pk} if case_pk else {}
        form = DocumentUploadForm(initial=initial)
    return render(request, "investigations/document_upload.html", {"form": form, "title": "Upload Document"})
