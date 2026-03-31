import hashlib
import json
import logging
from datetime import datetime, time

from django.db.models import Case as DbCase
from django.db.models import IntegerField, Max, Value, When
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import CaseForm, DocumentUploadForm
from .models import (
    Case,
    Detection,
    Document,
    DocumentType,
    GovernmentReferral,
    OcrStatus,
    Signal,
    SignalSeverity,
)
from .serializers import (
    CaseIntakeSerializer,
    CaseUpdateSerializer,
    DetectionIntakeSerializer,
    DetectionUpdateSerializer,
    DocumentIntakeSerializer,
    DocumentUpdateSerializer,
    ReferralIntakeSerializer,
    ReferralUpdateSerializer,
    SignalUpdateSerializer,
    serialize_case,
    serialize_case_detail,
    serialize_detection,
    serialize_document,
    serialize_referral,
    serialize_signal,
)

DEFAULT_PAGE_LIMIT = 25
MAX_BULK_FILES = 50


def _process_uploaded_file(
    uploaded_file, case, doc_type_hint="OTHER", source_url=None, run_pipeline=True
):
    """Run the full upload pipeline for a single InMemoryUploadedFile.

    Returns the saved Document instance. Raises on storage or DB errors;
    entity extraction and signal detection failures are swallowed (best-effort).
    """
    import hashlib as _hashlib

    from django.core.files.storage import default_storage

    sha = _hashlib.sha256()
    for chunk in uploaded_file.chunks():
        sha.update(chunk)
    sha256 = sha.hexdigest()

    relative_path = f"cases/{case.pk}/{uploaded_file.name}"
    saved_path = default_storage.save(relative_path, uploaded_file)

    extracted_text = ""
    ocr_status = OcrStatus.NOT_NEEDED
    processing_route = "non_pdf"
    if uploaded_file.name.lower().endswith(".pdf"):
        if run_pipeline:
            from .extraction import extract_from_pdf

            abs_path = default_storage.path(saved_path)
            extracted_text, ocr_status = extract_from_pdf(abs_path, file_size=uploaded_file.size)
            processing_route = f"pdf_{ocr_status.lower()}"
        else:
            # Bulk uploads prioritize persistence and responsiveness; heavy extraction runs later.
            ocr_status = OcrStatus.PENDING
            processing_route = "pdf_deferred"

    doc_type = doc_type_hint
    auto_classified = False
    if run_pipeline and doc_type == "OTHER" and extracted_text:
        from .classification import classify_document

        doc_type = classify_document(extracted_text)
        auto_classified = True

    is_generated = auto_classified and doc_type == DocumentType.REFERRAL_MEMO

    document = Document.objects.create(
        case=case,
        filename=uploaded_file.name,
        file_path=saved_path,
        sha256_hash=sha256,
        file_size=uploaded_file.size,
        doc_type=doc_type,
        is_generated=is_generated,
        source_url=source_url or None,
        extracted_text=extracted_text or None,
        ocr_status=ocr_status,
        uploaded_at=timezone.now(),
        updated_at=timezone.now(),
    )

    entity_summary = None
    if run_pipeline and extracted_text and not is_generated:
        try:
            from .entity_extraction import extract_entities
            from .entity_resolution import resolve_all_entities

            extraction_result = extract_entities(extracted_text, doc_type=doc_type)
            entity_summary = resolve_all_entities(extraction_result, case=case, document=document)
            if entity_summary.fuzzy_candidates:
                logger.info(
                    "entity_extraction_fuzzy_candidates",
                    extra={
                        "document_id": str(document.pk),
                        "case_id": str(case.pk),
                        "candidate_count": len(entity_summary.fuzzy_candidates),
                        "top_candidates": [
                            {
                                "incoming": c.incoming_raw,
                                "existing": c.existing_raw,
                                "similarity": c.similarity,
                                "type": c.entity_type,
                            }
                            for c in entity_summary.fuzzy_candidates[:5]
                        ],
                    },
                )
        except Exception:
            logger.exception(
                "entity_extraction_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )

    if run_pipeline:
        try:
            from .signal_rules import evaluate_case, evaluate_document, persist_signals

            # evaluate_document: doc-scoped rules (SR-001,002,005,006,011,012,013)
            # evaluate_case: case-scoped rules (SR-003,004,007,008,009,010) — called
            # after every upload so cross-document patterns are re-evaluated as
            # evidence accumulates, but dedup prevents re-persisting existing detections.
            all_triggers = evaluate_document(case, document) + evaluate_case(
                case, trigger_doc=document
            )
            persist_signals(case, all_triggers)
        except Exception:
            logger.exception(
                "signal_detection_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )

    logger.info(
        "document_upload_processed",
        extra={
            "document_id": str(document.pk),
            "case_id": str(case.pk),
            "uploaded_filename": uploaded_file.name,
            "file_size": uploaded_file.size,
            "processing_route": processing_route,
            "ocr_status": ocr_status,
            "doc_type": doc_type,
            "auto_classified": auto_classified,
            "is_generated": is_generated,
            "persons_created": entity_summary.persons_created if entity_summary else 0,
            "orgs_created": entity_summary.orgs_created if entity_summary else 0,
            "fuzzy_candidates": len(entity_summary.fuzzy_candidates) if entity_summary else 0,
        },
    )

    return document


def _process_existing_document(document: Document, case: Case) -> Document:
    """Run deferred processing for an existing uploaded document."""
    if not document.file_path:
        raise ValueError("Document has no stored file path.")

    from django.core.files.storage import default_storage

    extracted_text = document.extracted_text or ""
    ocr_status = document.ocr_status
    processing_route = "existing_non_pdf"

    if document.filename.lower().endswith(".pdf"):
        from .extraction import extract_from_pdf

        abs_path = default_storage.path(document.file_path)
        extracted_text, ocr_status = extract_from_pdf(abs_path, file_size=document.file_size)
        processing_route = f"existing_pdf_{ocr_status.lower()}"

    if document.doc_type == DocumentType.OTHER and extracted_text:
        from .classification import classify_document

        document.doc_type = classify_document(extracted_text)

    document.extracted_text = extracted_text or None
    document.ocr_status = ocr_status
    document.updated_at = timezone.now()
    document.save(update_fields=["doc_type", "extracted_text", "ocr_status", "updated_at"])

    entity_summary = None
    if extracted_text and not document.is_generated:
        try:
            from .entity_extraction import extract_entities
            from .entity_resolution import resolve_all_entities

            extraction_result = extract_entities(extracted_text, doc_type=document.doc_type)
            entity_summary = resolve_all_entities(extraction_result, case=case, document=document)
            if entity_summary.fuzzy_candidates:
                logger.info(
                    "entity_extraction_fuzzy_candidates_existing",
                    extra={
                        "document_id": str(document.pk),
                        "case_id": str(case.pk),
                        "candidate_count": len(entity_summary.fuzzy_candidates),
                    },
                )
        except Exception:
            logger.exception(
                "entity_extraction_failed_existing",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )

    try:
        from .signal_rules import evaluate_case, evaluate_document, persist_signals

        all_triggers = evaluate_document(case, document) + evaluate_case(case, trigger_doc=document)
        persist_signals(case, all_triggers)
    except Exception:
        logger.exception(
            "signal_detection_failed_existing",
            extra={"document_id": str(document.pk), "case_id": str(case.pk)},
        )

    logger.info(
        "document_existing_processed",
        extra={
            "document_id": str(document.pk),
            "case_id": str(case.pk),
            "processing_route": processing_route,
            "ocr_status": ocr_status,
            "doc_type": document.doc_type,
            "persons_created": entity_summary.persons_created if entity_summary else 0,
            "orgs_created": entity_summary.orgs_created if entity_summary else 0,
        },
    )

    return document


MAX_PAGE_LIMIT = 100

CASE_SORT_FIELDS = {"created_at", "name", "status", "id"}
DOCUMENT_SORT_FIELDS = {"uploaded_at", "filename", "file_size", "doc_type", "ocr_status", "id"}


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
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "non_field_errors": ["Query params 'limit' and 'offset' must be integers."]
                    }
                },
                status=400,
            ),
        )

    if limit < 1 or limit > MAX_PAGE_LIMIT:
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "non_field_errors": [f"'limit' must be between 1 and {MAX_PAGE_LIMIT}."]
                    }
                },
                status=400,
            ),
        )

    if offset < 0:
        return (
            None,
            None,
            JsonResponse(
                {"errors": {"non_field_errors": ["'offset' must be zero or greater."]}},
                status=400,
            ),
        )

    return limit, offset, None


def _parse_document_filters(request):
    raw_doc_type = request.GET.get("doc_type")
    raw_ocr_status = request.GET.get("ocr_status")

    valid_doc_types = {choice[0] for choice in Document._meta.get_field("doc_type").choices}
    valid_ocr_statuses = {choice[0] for choice in Document._meta.get_field("ocr_status").choices}

    if raw_doc_type and raw_doc_type not in valid_doc_types:
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "doc_type": [
                            f"Invalid doc_type. Expected one of: "
                            f"{', '.join(sorted(valid_doc_types))}."
                        ]
                    }
                },
                status=400,
            ),
        )

    if raw_ocr_status and raw_ocr_status not in valid_ocr_statuses:
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "ocr_status": [
                            "Invalid ocr_status. Expected one of: "
                            f"{', '.join(sorted(valid_ocr_statuses))}."
                        ]
                    }
                },
                status=400,
            ),
        )

    return raw_doc_type, raw_ocr_status, None


def _parse_case_filters(request):
    raw_status = request.GET.get("status")
    raw_query = request.GET.get("q")
    raw_created_from = request.GET.get("created_from")
    raw_created_to = request.GET.get("created_to")

    valid_statuses = {choice[0] for choice in Case._meta.get_field("status").choices}

    if raw_status and raw_status not in valid_statuses:
        return (
            None,
            None,
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "status": [
                            f"Invalid status. Expected one of: {', '.join(sorted(valid_statuses))}."
                        ]
                    }
                },
                status=400,
            ),
        )

    def _parse_datetime_bound(raw_value, field_name, is_end_of_day):
        return _parse_datetime_filter_bound(raw_value, field_name, is_end_of_day)

    created_from, from_error = _parse_datetime_bound(raw_created_from, "created_from", False)
    if from_error is not None:
        return None, None, None, None, from_error

    created_to, to_error = _parse_datetime_bound(raw_created_to, "created_to", True)
    if to_error is not None:
        return None, None, None, None, to_error

    if created_from and created_to and created_from > created_to:
        return (
            None,
            None,
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "non_field_errors": [
                            "'created_from' must be less than or equal to 'created_to'."
                        ]
                    }
                },
                status=400,
            ),
        )

    return raw_status, raw_query, created_from, created_to, None


def _parse_datetime_filter_bound(raw_value, field_name, is_end_of_day):
    if raw_value is None:
        return None, None

    parsed_datetime = parse_datetime(raw_value)
    if parsed_datetime is not None:
        if timezone.is_naive(parsed_datetime):
            parsed_datetime = timezone.make_aware(parsed_datetime, timezone.get_current_timezone())
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
                    "Expected ISO date or datetime "
                    "(for example 2026-03-26 or 2026-03-26T12:00:00Z)."
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

    uploaded_to, to_error = _parse_datetime_filter_bound(raw_uploaded_to, "uploaded_to", True)
    if to_error is not None:
        return None, None, to_error

    if uploaded_from and uploaded_to and uploaded_from > uploaded_to:
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "non_field_errors": [
                            "'uploaded_from' must be less than or equal to 'uploaded_to'."
                        ]
                    }
                },
                status=400,
            ),
        )

    return uploaded_from, uploaded_to, None


def _parse_sort_params(request, *, allowed_fields, default_field):
    raw_order_by = request.GET.get("order_by", default_field)
    raw_direction = request.GET.get("direction", "desc")

    if raw_order_by not in allowed_fields:
        return (
            None,
            None,
            JsonResponse(
                {
                    "errors": {
                        "order_by": [
                            f"Invalid order_by. Expected one of: "
                            f"{', '.join(sorted(allowed_fields))}."
                        ]
                    }
                },
                status=400,
            ),
        )

    if raw_direction not in {"asc", "desc"}:
        return (
            None,
            None,
            JsonResponse(
                {"errors": {"direction": ["Invalid direction. Expected 'asc' or 'desc'."]}},
                status=400,
            ),
        )

    return raw_order_by, raw_direction, None


def _build_ordering_fields(order_by, direction):
    prefix = "" if direction == "asc" else "-"
    ordering = [f"{prefix}{order_by}"]
    if order_by != "id":
        ordering.append(f"{prefix}id")
    return ordering


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_case_collection(request):
    if request.method == "GET":
        limit, offset, pagination_error = _parse_limit_offset(request)
        if pagination_error is not None:
            return pagination_error

        status_filter, query_filter, created_from, created_to, filter_error = _parse_case_filters(
            request
        )
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
        paged_cases = cases[offset : offset + limit]
        next_offset = offset + limit if (offset + limit) < total_count else None
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


@csrf_exempt
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
                        "non_field_errors": ["Case cannot be deleted while related records exist."]
                    }
                },
                status=409,
            )
        return HttpResponse(status=204)

    return JsonResponse(serialize_case_detail(case))


@csrf_exempt
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

        uploaded_from, uploaded_to, date_filter_error = _parse_document_date_filters(request)
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
        paged_documents = documents[offset : offset + limit]
        next_offset = offset + limit if (offset + limit) < total_count else None
        previous_offset = max(offset - limit, 0) if offset > 0 else None

        return JsonResponse(
            {
                "count": total_count,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
                "previous_offset": previous_offset,
                "results": [serialize_document(document) for document in paged_documents],
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


@csrf_exempt
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


# ---------------------------------------------------------------------------
# Signal API endpoints
# ---------------------------------------------------------------------------

SIGNAL_SORT_FIELDS = {"detected_at", "severity", "status", "rule_id", "id"}


@csrf_exempt
@require_http_methods(["GET"])
def api_case_signal_collection(request, pk):
    case = get_object_or_404(Case, pk=pk)

    limit, offset, pagination_error = _parse_limit_offset(request)
    if pagination_error is not None:
        return pagination_error

    order_by, direction, sort_error = _parse_sort_params(
        request,
        allowed_fields=SIGNAL_SORT_FIELDS,
        default_field="detected_at",
    )
    if sort_error is not None:
        return sort_error

    ordering = _build_ordering_fields(order_by, direction)
    signals_qs = Signal.objects.filter(case=case).order_by(*ordering)

    # Optional filters
    raw_status = request.GET.get("status")
    if raw_status is not None:
        valid_statuses = {c[0] for c in Signal._meta.get_field("status").choices}
        if raw_status not in valid_statuses:
            return JsonResponse(
                {
                    "errors": {
                        "status": [
                            f"Invalid status. Expected one of: {', '.join(sorted(valid_statuses))}."
                        ]
                    }
                },
                status=400,
            )
        signals_qs = signals_qs.filter(status=raw_status)

    raw_severity = request.GET.get("severity")
    if raw_severity is not None:
        valid_severities = {c[0] for c in Signal._meta.get_field("severity").choices}
        if raw_severity not in valid_severities:
            return JsonResponse(
                {
                    "errors": {
                        "severity": [
                            f"Invalid severity. Expected one of: "
                            f"{', '.join(sorted(valid_severities))}."
                        ]
                    }
                },
                status=400,
            )
        signals_qs = signals_qs.filter(severity=raw_severity)

    raw_rule_id = request.GET.get("rule_id")
    if raw_rule_id is not None:
        signals_qs = signals_qs.filter(rule_id=raw_rule_id)

    total_count = signals_qs.count()
    paged = signals_qs[offset : offset + limit]
    next_offset = offset + limit if (offset + limit) < total_count else None
    previous_offset = max(offset - limit, 0) if offset > 0 else None

    return JsonResponse(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "previous_offset": previous_offset,
            "results": [serialize_signal(s) for s in paged],
        }
    )


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def api_case_signal_detail(request, pk, signal_id):
    case = get_object_or_404(Case, pk=pk)
    signal = get_object_or_404(Signal, pk=signal_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = SignalUpdateSerializer(data=payload, instance=signal)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)

    return JsonResponse(serialize_signal(signal))


_SEVERITY_RANK = {
    SignalSeverity.CRITICAL: 4,
    SignalSeverity.HIGH: 3,
    SignalSeverity.MEDIUM: 2,
    SignalSeverity.LOW: 1,
}

_RANK_TO_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}


@csrf_exempt
@require_http_methods(["GET"])
def api_signal_summary(request):
    """Return the highest open signal severity per case.

    Response shape:
      { "results": [{ "case_id": "<uuid>", "highest_severity": "HIGH", "open_count": 3 }, ...] }

    Only cases that have at least one signal are included. Cases with no
    signals are omitted — the frontend treats absence as no severity badge.
    """
    severity_expr = DbCase(
        When(severity=SignalSeverity.CRITICAL, then=Value(4)),
        When(severity=SignalSeverity.HIGH, then=Value(3)),
        When(severity=SignalSeverity.MEDIUM, then=Value(2)),
        When(severity=SignalSeverity.LOW, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )

    from django.db.models import Count, Q

    rows = (
        Signal.objects.values("case_id")
        .annotate(
            max_rank=Max(severity_expr),
            open_count=Count("id", filter=Q(status="OPEN")),
        )
        .filter(max_rank__gt=0)
    )

    results = [
        {
            "case_id": str(row["case_id"]),
            "highest_severity": _RANK_TO_SEVERITY.get(row["max_rank"], "LOW"),
            "open_count": row["open_count"],
        }
        for row in rows
    ]

    return JsonResponse({"results": results})


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
    return render(
        request, "investigations/case_detail.html", {"case": case, "documents": documents}
    )


def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            _process_uploaded_file(
                uploaded_file=request.FILES["file"],
                case=form.cleaned_data["case"],
                doc_type_hint=form.cleaned_data["doc_type"],
                source_url=form.cleaned_data.get("source_url"),
            )
            return redirect("case_detail", pk=form.cleaned_data["case"].pk)
    else:
        case_pk = request.GET.get("case")
        initial = {"case": case_pk} if case_pk else {}
        form = DocumentUploadForm(initial=initial)
    return render(
        request, "investigations/document_upload.html", {"form": form, "title": "Upload Document"}
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_case_document_bulk_upload(request, pk):
    """Accept up to MAX_BULK_FILES files in a single multipart POST.

    Each file is processed through the full pipeline (OCR, classification,
    entity extraction, signal detection). Results are returned as a list so
    the frontend can report per-file success or failure.

    Request: multipart/form-data with one or more fields named "files"
    Response: { "created": [...serialized docs...], "errors": [...] }
    """
    case = get_object_or_404(Case, pk=pk)

    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse(
            {
                "errors": {
                    "non_field_errors": [
                        "No files provided. Send files as multipart field 'files'."
                    ]
                }
            },
            status=400,
        )

    if len(files) > MAX_BULK_FILES:
        return JsonResponse(
            {"errors": {"non_field_errors": [f"Maximum {MAX_BULK_FILES} files per request."]}},
            status=400,
        )

    created = []
    errors = []

    for uploaded_file in files:
        try:
            document = _process_uploaded_file(
                uploaded_file=uploaded_file,
                case=case,
                doc_type_hint="OTHER",
                run_pipeline=False,
            )
            created.append(serialize_document(document))
        except Exception as exc:
            logger.exception(
                "bulk_upload_file_failed",
                extra={"case_id": str(case.pk), "filename": uploaded_file.name},
            )
            errors.append({"filename": uploaded_file.name, "error": str(exc)})

    status_code = 201 if created else 400
    return JsonResponse({"created": created, "errors": errors}, status=status_code)


@csrf_exempt
@require_http_methods(["POST"])
def api_case_document_process_pending(request, pk):
    """Process pending OCR documents for a case on demand."""
    case = get_object_or_404(Case, pk=pk)

    pending_documents = list(
        case.documents.filter(ocr_status=OcrStatus.PENDING).order_by("uploaded_at")
    )

    processed = []
    errors = []

    for document in pending_documents:
        try:
            updated = _process_existing_document(document, case)
            processed.append(serialize_document(updated))
        except Exception as exc:
            logger.exception(
                "process_pending_ocr_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )
            errors.append(
                {
                    "document_id": str(document.pk),
                    "filename": document.filename,
                    "error": str(exc),
                }
            )

    return JsonResponse(
        {
            "requested": len(pending_documents),
            "processed": processed,
            "errors": errors,
            "skipped": max(0, len(pending_documents) - len(processed) - len(errors)),
        }
    )


# ---------------------------------------------------------------------------
# Government Referral API
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_case_referral_collection(request, pk):
    case = get_object_or_404(Case, pk=pk)

    if request.method == "GET":
        referrals = case.referrals.order_by("-filing_date")
        return JsonResponse({"results": [serialize_referral(r) for r in referrals]})

    payload, error_response = _parse_json_body(request)
    if error_response is not None:
        return error_response

    serializer = ReferralIntakeSerializer(data=payload, case=case)
    if not serializer.is_valid():
        return JsonResponse({"errors": serializer.errors}, status=400)

    serializer.save()
    return JsonResponse(serializer.data, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_referral_detail(request, pk, referral_id):
    case = get_object_or_404(Case, pk=pk)
    referral = get_object_or_404(GovernmentReferral, referral_id=referral_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = ReferralUpdateSerializer(data=payload, instance=referral)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        referral.delete()
        return HttpResponse(status=204)

    return JsonResponse(serialize_referral(referral))


# ---------------------------------------------------------------------------
# Referral memo generation
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def api_case_referral_memo(request, pk):
    """Generate a REFERRAL_MEMO document for a case.

    Builds a plain-text memo from the case's current state (name, status,
    referral ref, notes) and stores it as a generated Document record so it
    appears in the documents panel alongside uploaded evidence.
    """
    import uuid as _uuid

    case = get_object_or_404(Case, pk=pk)

    referrals = list(case.referrals.order_by("-filing_date"))
    referral_lines = []
    for r in referrals:
        line = f"  - {r.agency_name or 'Unknown Agency'} | Status: {r.status}"
        if r.submission_id:
            line += f" | Ref: {r.submission_id}"
        referral_lines.append(line)

    from django.utils import timezone as tz

    now_str = tz.now().strftime("%Y-%m-%d %H:%M UTC")

    memo_lines = [
        "REFERRAL MEMO",
        "=" * 60,
        f"Case:        {case.name}",
        f"Case ID:     {case.pk}",
        f"Status:      {case.status}",
        f"Referral Ref:{' ' + case.referral_ref if case.referral_ref else ' —'}",
        f"Notes:       {case.notes or '—'}",
        "",
        f"Government Referrals ({len(referrals)}):",
    ]
    if referral_lines:
        memo_lines.extend(referral_lines)
    else:
        memo_lines.append("  (none)")

    memo_lines += [
        "",
        f"Generated:   {now_str}",
        "=" * 60,
    ]

    memo_text = "\n".join(memo_lines)

    # Store as a pseudo-file document (no physical file — text stored inline)
    fake_hash = hashlib.sha256(memo_text.encode()).hexdigest()
    filename = f"referral_memo_{case.pk}_{_uuid.uuid4().hex[:8]}.txt"

    document = Document.objects.create(
        case=case,
        filename=filename,
        file_path="",
        sha256_hash=fake_hash,
        file_size=len(memo_text.encode()),
        doc_type=DocumentType.REFERRAL_MEMO,
        is_generated=True,
        doc_subtype="auto_generated",
        extracted_text=memo_text,
        ocr_status=OcrStatus.NOT_NEEDED,
        uploaded_at=tz.now(),
        updated_at=tz.now(),
    )

    return JsonResponse(serialize_document(document), status=201)


# ---------------------------------------------------------------------------
# Detection API endpoints
# ---------------------------------------------------------------------------

DETECTION_SORT_FIELDS = {"detected_at", "severity", "status", "signal_type", "id"}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_case_detection_collection(request, pk):
    """
    GET  /api/cases/<uuid>/detections/  — list detections for a case
    POST /api/cases/<uuid>/detections/  — create an investigator-manual detection
    """
    case = get_object_or_404(Case, pk=pk)

    if request.method == "POST":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = DetectionIntakeSerializer(data=payload, case=case)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data, status=201)

    # GET
    limit, offset, pagination_error = _parse_limit_offset(request)
    if pagination_error is not None:
        return pagination_error

    order_by, direction, sort_error = _parse_sort_params(
        request,
        allowed_fields=DETECTION_SORT_FIELDS,
        default_field="detected_at",
    )
    if sort_error is not None:
        return sort_error

    ordering = _build_ordering_fields(order_by, direction)
    qs = Detection.objects.filter(case=case).order_by(*ordering)

    raw_status = request.GET.get("status")
    if raw_status is not None:
        valid_statuses = {c[0] for c in Detection._meta.get_field("status").choices}
        if raw_status not in valid_statuses:
            return JsonResponse(
                {
                    "errors": {
                        "status": [
                            f"Invalid status. Expected one of: {', '.join(sorted(valid_statuses))}."
                        ]
                    }
                },
                status=400,
            )
        qs = qs.filter(status=raw_status)

    raw_severity = request.GET.get("severity")
    if raw_severity is not None:
        valid_severities = {c[0] for c in Detection._meta.get_field("severity").choices}
        if raw_severity not in valid_severities:
            return JsonResponse(
                {
                    "errors": {
                        "severity": [
                            f"Invalid severity. Expected one of: "
                            f"{', '.join(sorted(valid_severities))}."
                        ]
                    }
                },
                status=400,
            )
        qs = qs.filter(severity=raw_severity)

    raw_signal_type = request.GET.get("signal_type")
    if raw_signal_type is not None:
        qs = qs.filter(signal_type=raw_signal_type)

    total_count = qs.count()
    paged = qs[offset : offset + limit]
    next_offset = offset + limit if (offset + limit) < total_count else None
    previous_offset = max(offset - limit, 0) if offset > 0 else None

    return JsonResponse(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "previous_offset": previous_offset,
            "results": [serialize_detection(d) for d in paged],
        }
    )


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_detection_detail(request, pk, detection_id):
    """
    GET    /api/cases/<uuid>/detections/<uuid>/  — detection detail
    PATCH  /api/cases/<uuid>/detections/<uuid>/  — update status / note / confidence
    DELETE /api/cases/<uuid>/detections/<uuid>/  — remove detection
    """
    case = get_object_or_404(Case, pk=pk)
    detection = get_object_or_404(Detection, pk=detection_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = DetectionUpdateSerializer(data=payload, instance=detection)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        detection.delete()
        return HttpResponse(status=204)

    return JsonResponse(serialize_detection(detection))


# ---------------------------------------------------------------------------
# Signal Re-evaluation API
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def api_case_reevaluate_signals(request, pk):
    """Re-run all signal rules against every document in a case.

    Useful when:
      - Bulk-uploaded documents have been OCR-processed after upload
      - Entities (persons, orgs, properties) were added or corrected manually
      - The investigator wants to confirm that all signals are up to date

    Deduplication in persist_signals() prevents duplicate detections.

    Response: { "new_detections": [...], "documents_evaluated": N }
    """
    case = get_object_or_404(Case, pk=pk)

    from .signal_rules import evaluate_case, evaluate_document, persist_signals

    all_new = []

    documents = list(case.documents.filter(extracted_text__isnull=False).order_by("uploaded_at"))

    for document in documents:
        try:
            doc_triggers = evaluate_document(case, document)
            persist_result = persist_signals(case, doc_triggers)
            all_new.extend(persist_result)
        except Exception:
            logger.exception(
                "reevaluate_document_signals_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )

    try:
        case_triggers = evaluate_case(case)
        persist_result = persist_signals(case, case_triggers)
        all_new.extend(persist_result)
    except Exception:
        logger.exception(
            "reevaluate_case_signals_failed",
            extra={"case_id": str(case.pk)},
        )

    return JsonResponse(
        {
            "documents_evaluated": len(documents),
            "new_detections": [serialize_detection(d) for d in all_new],
        }
    )
