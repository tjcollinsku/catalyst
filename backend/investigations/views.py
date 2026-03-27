import json
import hashlib
import logging
from datetime import datetime, time

from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import CaseForm, DocumentUploadForm
from .models import Case, Document, DocumentType, OcrStatus
from .serializers import (
    CaseIntakeSerializer,
    CaseUpdateSerializer,
    DocumentIntakeSerializer,
    DocumentUpdateSerializer,
    serialize_case,
    serialize_case_detail,
    serialize_document,
)


DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100

CASE_SORT_FIELDS = {"created_at", "name", "status", "id"}
DOCUMENT_SORT_FIELDS = {"uploaded_at", "filename",
                        "file_size", "doc_type", "ocr_status", "id"}


logger = logging.getLogger("investigations.upload_pipeline")


def _parse_json_body(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, JsonResponse(
            {"errors": {"non_field_errors": ["Malformed JSON body."]}},
            status=400,
        )

    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"errors": {"non_field_errors": ["Expected a JSON object."]}},
            status=400,
        )

    return payload, None


def _parse_limit_offset(request):
    raw_limit = request.GET.get("limit", str(DEFAULT_PAGE_LIMIT))
    raw_offset = request.GET.get("offset", "0")

    try:
        limit = int(raw_limit)
        offset = int(raw_offset)
    except (TypeError, ValueError):
        return None, None, JsonResponse(
            {
                "errors": {
                    "non_field_errors": [
                        "Query params 'limit' and 'offset' must be integers."
                    ]
                }
            },
            status=400,
        )

    if limit < 1 or limit > MAX_PAGE_LIMIT:
        return None, None, JsonResponse(
            {
                "errors": {
                    "non_field_errors": [
                        f"'limit' must be between 1 and {MAX_PAGE_LIMIT}."
                    ]
                }
            },
            status=400,
        )

    if offset < 0:
        return None, None, JsonResponse(
            {
                "errors": {
                    "non_field_errors": ["'offset' must be zero or greater."]
                }
            },
            status=400,
        )

    return limit, offset, None


def _parse_document_filters(request):
    raw_doc_type = request.GET.get("doc_type")
    raw_ocr_status = request.GET.get("ocr_status")

    valid_doc_types = {choice[0]
                       for choice in Document._meta.get_field("doc_type").choices}
    valid_ocr_statuses = {
        choice[0] for choice in Document._meta.get_field("ocr_status").choices
    }

    if raw_doc_type and raw_doc_type not in valid_doc_types:
        return None, None, JsonResponse(
            {
                "errors": {
                    "doc_type": [
                        f"Invalid doc_type. Expected one of: {', '.join(sorted(valid_doc_types))}."
                    ]
                }
            },
            status=400,
        )

    if raw_ocr_status and raw_ocr_status not in valid_ocr_statuses:
        return None, None, JsonResponse(
            {
                "errors": {
                    "ocr_status": [
                        "Invalid ocr_status. Expected one of: "
                        f"{', '.join(sorted(valid_ocr_statuses))}."
                    ]
                }
            },
            status=400,
        )

    return raw_doc_type, raw_ocr_status, None


def _parse_case_filters(request):
    raw_status = request.GET.get("status")
    raw_query = request.GET.get("q")
    raw_created_from = request.GET.get("created_from")
    raw_created_to = request.GET.get("created_to")

    valid_statuses = {choice[0]
                      for choice in Case._meta.get_field("status").choices}

    if raw_status and raw_status not in valid_statuses:
        return None, None, None, None, JsonResponse(
            {
                "errors": {
                    "status": [
                        f"Invalid status. Expected one of: {', '.join(sorted(valid_statuses))}."
                    ]
                }
            },
            status=400,
        )

    def _parse_datetime_bound(raw_value, field_name, is_end_of_day):
        return _parse_datetime_filter_bound(raw_value, field_name, is_end_of_day)

    created_from, from_error = _parse_datetime_bound(
        raw_created_from, "created_from", False
    )
    if from_error is not None:
        return None, None, None, None, from_error

    created_to, to_error = _parse_datetime_bound(
        raw_created_to, "created_to", True)
    if to_error is not None:
        return None, None, None, None, to_error

    if created_from and created_to and created_from > created_to:
        return None, None, None, None, JsonResponse(
            {
                "errors": {
                    "non_field_errors": [
                        "'created_from' must be less than or equal to 'created_to'."
                    ]
                }
            },
            status=400,
        )

    return raw_status, raw_query, created_from, created_to, None


def _parse_datetime_filter_bound(raw_value, field_name, is_end_of_day):
    if raw_value is None:
        return None, None

    parsed_datetime = parse_datetime(raw_value)
    if parsed_datetime is not None:
        if timezone.is_naive(parsed_datetime):
            parsed_datetime = timezone.make_aware(
                parsed_datetime, timezone.get_current_timezone()
            )
        return parsed_datetime, None

    parsed_date = parse_date(raw_value)
    if parsed_date is not None:
        day_time = time.max if is_end_of_day else time.min
        combined = datetime.combine(parsed_date, day_time)
        return timezone.make_aware(combined, timezone.get_current_timezone()), None

    return None, JsonResponse(
        {
            "errors": {
                field_name: [
                    "Expected ISO date or datetime (for example 2026-03-26 or 2026-03-26T12:00:00Z)."
                ]
            }
        },
        status=400,
    )


def _parse_document_date_filters(request):
    raw_uploaded_from = request.GET.get("uploaded_from")
    raw_uploaded_to = request.GET.get("uploaded_to")

    uploaded_from, from_error = _parse_datetime_filter_bound(
        raw_uploaded_from, "uploaded_from", False
    )
    if from_error is not None:
        return None, None, from_error

    uploaded_to, to_error = _parse_datetime_filter_bound(
        raw_uploaded_to, "uploaded_to", True
    )
    if to_error is not None:
        return None, None, to_error

    if uploaded_from and uploaded_to and uploaded_from > uploaded_to:
        return None, None, JsonResponse(
            {
                "errors": {
                    "non_field_errors": [
                        "'uploaded_from' must be less than or equal to 'uploaded_to'."
                    ]
                }
            },
            status=400,
        )

    return uploaded_from, uploaded_to, None


def _parse_sort_params(request, *, allowed_fields, default_field):
    raw_order_by = request.GET.get("order_by", default_field)
    raw_direction = request.GET.get("direction", "desc")

    if raw_order_by not in allowed_fields:
        return None, None, JsonResponse(
            {
                "errors": {
                    "order_by": [
                        f"Invalid order_by. Expected one of: {', '.join(sorted(allowed_fields))}."
                    ]
                }
            },
            status=400,
        )

    if raw_direction not in {"asc", "desc"}:
        return None, None, JsonResponse(
            {
                "errors": {
                    "direction": ["Invalid direction. Expected 'asc' or 'desc'."]
                }
            },
            status=400,
        )

    return raw_order_by, raw_direction, None


def _build_ordering_fields(order_by, direction):
    prefix = "" if direction == "asc" else "-"
    ordering = [f"{prefix}{order_by}"]
    if order_by != "id":
        ordering.append(f"{prefix}id")
    return ordering


@require_http_methods(["GET", "POST"])
def api_case_collection(request):
    if request.method == "GET":
        limit, offset, pagination_error = _parse_limit_offset(request)
        if pagination_error is not None:
            return pagination_error

        status_filter, query_filter, created_from, created_to, filter_error = _parse_case_filters(
            request)
        if filter_error is not None:
            return filter_error

        order_by, direction, sort_error = _parse_sort_params(
            request,
            allowed_fields=CASE_SORT_FIELDS,
            default_field="created_at",
        )
        if sort_error is not None:
            return sort_error

        ordering = _build_ordering_fields(order_by, direction)

        cases = Case.objects.order_by(*ordering)
        if status_filter is not None:
            cases = cases.filter(status=status_filter)
        if query_filter:
            cases = cases.filter(name__icontains=query_filter)
        if created_from is not None:
            cases = cases.filter(created_at__gte=created_from)
        if created_to is not None:
            cases = cases.filter(created_at__lte=created_to)

        total_count = cases.count()
        paged_cases = cases[offset:offset + limit]
        next_offset = offset + \
            limit if (offset + limit) < total_count else None
        previous_offset = max(offset - limit, 0) if offset > 0 else None

        return JsonResponse(
            {
                "count": total_count,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "previous_offset": previous_offset,
                "results": [serialize_case(case) for case in paged_cases],
            }
        )

    payload, error_response = _parse_json_body(request)
    if error_response is not None:
        return error_response

    serializer = CaseIntakeSerializer(data=payload)
    if not serializer.is_valid():
        return JsonResponse({"errors": serializer.errors}, status=400)

    serializer.save()
    return JsonResponse(serializer.data, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_detail(request, pk):
    case = get_object_or_404(Case, pk=pk)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = CaseUpdateSerializer(data=payload, instance=case)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        try:
            case.delete()
        except (ProtectedError, RestrictedError):
            return JsonResponse(
                {
                    "errors": {
                        "non_field_errors": [
                            "Case cannot be deleted while related records exist."
                        ]
                    }
                },
                status=409,
            )
        return HttpResponse(status=204)

    return JsonResponse(serialize_case_detail(case))


@require_http_methods(["GET", "POST"])
def api_case_document_collection(request, pk):
    case = get_object_or_404(Case, pk=pk)

    if request.method == "GET":
        limit, offset, pagination_error = _parse_limit_offset(request)
        if pagination_error is not None:
            return pagination_error

        doc_type, ocr_status, filter_error = _parse_document_filters(request)
        if filter_error is not None:
            return filter_error

        uploaded_from, uploaded_to, date_filter_error = _parse_document_date_filters(
            request
        )
        if date_filter_error is not None:
            return date_filter_error

        order_by, direction, sort_error = _parse_sort_params(
            request,
            allowed_fields=DOCUMENT_SORT_FIELDS,
            default_field="uploaded_at",
        )
        if sort_error is not None:
            return sort_error

        ordering = _build_ordering_fields(order_by, direction)

        documents = case.documents.order_by(*ordering)
        if doc_type is not None:
            documents = documents.filter(doc_type=doc_type)
        if ocr_status is not None:
            documents = documents.filter(ocr_status=ocr_status)
        if uploaded_from is not None:
            documents = documents.filter(uploaded_at__gte=uploaded_from)
        if uploaded_to is not None:
            documents = documents.filter(uploaded_at__lte=uploaded_to)

        total_count = documents.count()
        paged_documents = documents[offset:offset + limit]
        next_offset = offset + \
            limit if (offset + limit) < total_count else None
        previous_offset = max(offset - limit, 0) if offset > 0 else None

        return JsonResponse(
            {
                "count": total_count,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "previous_offset": previous_offset,
                "results": [
                    serialize_document(document) for document in paged_documents
                ],
            }
        )

    payload, error_response = _parse_json_body(request)
    if error_response is not None:
        return error_response

    serializer = DocumentIntakeSerializer(data=payload, case=case)
    if not serializer.is_valid():
        return JsonResponse({"errors": serializer.errors}, status=400)

    serializer.save()
    return JsonResponse(serializer.data, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_document_detail(request, pk, document_id):
    case = get_object_or_404(Case, pk=pk)
    document = get_object_or_404(Document, pk=document_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = DocumentUpdateSerializer(data=payload, instance=document)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        document.delete()
        return HttpResponse(status=204)

    return JsonResponse(serialize_document(document))


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

            # Attempt text extraction for PDF files
            extracted_text = ""
            ocr_status = OcrStatus.PENDING
            processing_route = "non_pdf"
            if uploaded.name.lower().endswith(".pdf"):
                from .extraction import extract_from_pdf
                abs_path = default_storage.path(saved_path)
                extracted_text, ocr_status = extract_from_pdf(
                    abs_path, file_size=uploaded.size)
                processing_route = f"pdf_{ocr_status.lower()}"
            else:
                ocr_status = OcrStatus.NOT_NEEDED

            # Auto-classify doc_type when user left it as OTHER
            doc_type = form.cleaned_data["doc_type"]
            auto_classified = False
            if doc_type == "OTHER" and extracted_text:
                from .classification import classify_document
                doc_type = classify_document(extracted_text)
                auto_classified = True

            is_generated = (
                auto_classified and doc_type == DocumentType.REFERRAL_MEMO
            )

            document = Document.objects.create(
                case=case,
                filename=uploaded.name,
                file_path=saved_path,
                sha256_hash=sha256,
                file_size=uploaded.size,
                doc_type=doc_type,
                is_generated=is_generated,
                source_url=form.cleaned_data.get("source_url") or None,
                extracted_text=extracted_text or None,
                ocr_status=ocr_status,
                uploaded_at=timezone.now(),
                updated_at=timezone.now(),
            )

            logger.info(
                "document_upload_processed",
                extra={
                    "document_id": str(document.pk),
                    "case_id": str(case.pk),
                    "uploaded_filename": uploaded.name,
                    "file_size": uploaded.size,
                    "processing_route": processing_route,
                    "ocr_status": ocr_status,
                    "doc_type": doc_type,
                    "auto_classified": auto_classified,
                    "is_generated": is_generated,
                },
            )
            return redirect("case_detail", pk=case.pk)
    else:
        case_pk = request.GET.get("case")
        initial = {"case": case_pk} if case_pk else {}
        form = DocumentUploadForm(initial=initial)
    return render(request, "investigations/document_upload.html", {"form": form, "title": "Upload Document"})
