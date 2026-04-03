import hashlib
import json
import logging
from datetime import datetime, time

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Case as DbCase
from django.db.models import Count, IntegerField, Max, Q, Value, When
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .forms import CaseForm, DocumentUploadForm
from .models import (
    AuditAction,
    AuditLog,
    Case,
    Detection,
    Document,
    DocumentType,
    EntitySignal,
    FinancialInstrument,
    Finding,
    FindingEntity,
    GovernmentReferral,
    InvestigatorNote,
    OcrStatus,
    Organization,
    OrgDocument,
    Person,
    PersonDocument,
    PersonOrganization,
    Property,
    PropertyTransaction,
    Relationship,
    Signal,
    SignalSeverity,
    SocialMediaConnection,
)
from .serializers import (
    CaseIntakeSerializer,
    CaseUpdateSerializer,
    DetectionIntakeSerializer,
    DetectionUpdateSerializer,
    DocumentIntakeSerializer,
    DocumentUpdateSerializer,
    FindingIntakeSerializer,
    FindingUpdateSerializer,
    NoteIntakeSerializer,
    NoteUpdateSerializer,
    ReferralIntakeSerializer,
    ReferralUpdateSerializer,
    SignalUpdateSerializer,
    serialize_audit_log,
    serialize_case,
    serialize_case_detail,
    serialize_detection,
    serialize_document,
    serialize_financial_instrument,
    serialize_finding,
    serialize_note,
    serialize_organization,
    serialize_person,
    serialize_property,
    serialize_referral,
    serialize_signal,
)

DEFAULT_PAGE_LIMIT = 25
MAX_BULK_FILES = 50


def _save_financial_snapshot(document, case, financials, meta):
    """Persist extracted 990 financial data to FinancialSnapshot model."""
    from .models import FinancialSnapshot, Organization

    # Map extraction keys to model field names
    _KEY_MAP = {
        "contributions_and_grants": "total_contributions",
        "program_service_revenue": "program_service_revenue",
        "investment_income": "investment_income",
        "other_revenue": "other_revenue",
        "total_revenue": "total_revenue",
        "grants_paid": "grants_paid",
        "salaries_and_compensation": "salaries_and_compensation",
        "professional_fundraising": "professional_fundraising",
        "other_expenses": "other_expenses",
        "total_expenses": "total_expenses",
        "revenue_less_expenses": "revenue_less_expenses",
        "total_assets": "total_assets_eoy",
        "total_liabilities": "total_liabilities_eoy",
        "net_assets": "net_assets_eoy",
    }

    # Extract tax year from filename (e.g. "990_2024_...") or meta
    import re

    tax_year = None
    m = re.search(r"(\d{4})", document.filename)
    if m:
        yr = int(m.group(1))
        if 2000 <= yr <= 2030:
            tax_year = yr
    if not tax_year:
        return

    # Build defaults dict from financials
    defaults = {
        "case": case,
        "ein": meta.get("org_ein", ""),
        "source": "EXTRACTED",
        "raw_extraction": {"financials": financials, "meta": meta},
    }

    # Map current_year values
    for item in financials:
        model_field = _KEY_MAP.get(item["key"])
        if model_field and item.get("current_year") is not None:
            defaults[model_field] = item["current_year"]

    # Also store prior_year values as BOY where applicable
    for item in financials:
        if item["key"] == "total_assets" and item.get("prior_year") is not None:
            defaults["total_assets_boy"] = item["prior_year"]
        elif item["key"] == "total_liabilities" and item.get("prior_year") is not None:
            defaults["total_liabilities_boy"] = item["prior_year"]
        elif item["key"] == "net_assets" and item.get("prior_year") is not None:
            defaults["net_assets_boy"] = item["prior_year"]

    # Try to find the org this 990 belongs to
    ein = meta.get("org_ein", "")
    if ein:
        org = Organization.objects.filter(case=case, ein=ein).first()
        if org:
            defaults["organization"] = org

    # Calculate confidence based on how many key fields we got
    key_fields = ["total_revenue", "total_expenses", "total_assets_eoy", "net_assets_eoy"]
    filled = sum(1 for f in key_fields if defaults.get(f) is not None)
    defaults["confidence"] = round(filled / len(key_fields), 2)

    FinancialSnapshot.objects.update_or_create(
        document=document,
        tax_year=tax_year,
        defaults=defaults,
    )
    logger.info(
        "financial_snapshot_saved",
        extra={
            "document_id": str(document.pk),
            "tax_year": tax_year,
            "confidence": defaults["confidence"],
            "fields_extracted": filled,
        },
    )


def _generate_forensic_filename(
    doc_type: str,
    extracted_text: str,
    original_filename: str,
) -> str:
    """
    Generate a forensic canonical filename following the schema:
        YYYY-MM-DD_Entity_DocType.ext

    Examples:
        2022-09-15_DoGood-In-His-Name-Inc_Parcel-Record.pdf
        2018-01-23_DoGood-In-His-Name_SOS-Articles-of-Inc.pdf
        2017-09-01_Hoelscher-LLC_Warranty-Deed.pdf

    Uses extracted text to find the most relevant date and primary entity.
    Falls back to 0000-00-00 for date and "Unknown" for entity if not found.

    The original filename is preserved in the Document.filename field for
    chain-of-custody. This canonical name goes in Document.display_name.
    """
    import os
    import re as _re

    # --- Determine file extension ---
    _, ext = os.path.splitext(original_filename)
    ext = ext.lower() or ".pdf"

    # --- Extract the best date and entity ---
    date_str = "0000-00-00"
    entity = "Unknown"

    if extracted_text:
        from .entity_extraction import extract_entities

        result = extract_entities(extracted_text, doc_type=doc_type)

        # --- Date selection ---
        # For parcel records, prefer the SOLD date (most forensically relevant)
        if doc_type == "PARCEL_RECORD":
            sold_match = _re.search(r"SOLD:\s+(\d{1,2})/(\d{1,2})/(\d{4})", extracted_text)
            if sold_match:
                m, d, y = sold_match.group(1), sold_match.group(2), sold_match.group(3)
                yr = int(y)
                if yr >= 1950:  # skip placeholder dates like 11/11/1900
                    date_str = f"{yr}-{int(m):02d}-{int(d):02d}"

        # Fall back to first normalized date from entity extraction
        if date_str == "0000-00-00":
            for d in result.get("dates", []):
                if d.get("normalized"):
                    date_str = d["normalized"]
                    break

        # --- Entity selection ---
        # For parcel records, get owner directly from the label-value pattern
        # (ALL-CAPS owner names don't match the title-case org regex)
        if doc_type == "PARCEL_RECORD":
            owner_match = _re.search(r"Owner\s*\n\s*(.+?)$", extracted_text, _re.MULTILINE)
            if owner_match:
                entity = owner_match.group(1).strip()

        # For deeds, prefer grantee (the new owner)
        if doc_type == "DEED" and entity == "Unknown":
            grantee_match = _re.search(
                r"GRANTEE\s*[:\-]?\s*(.+?)$", extracted_text, _re.MULTILINE | _re.IGNORECASE
            )
            if grantee_match:
                entity = grantee_match.group(1).strip()

        # Fall back to entity extraction results
        if entity == "Unknown":
            orgs = result.get("orgs", [])
            if orgs:
                entity = orgs[0]["raw"]
            else:
                persons = result.get("persons", [])
                if persons:
                    entity = persons[0]["raw"]

    # --- Build doc type label ---
    _DOC_TYPE_LABELS = {
        "DEED": "Deed",
        "PARCEL_RECORD": "Parcel-Record",
        "IRS_990": "IRS-Form-990",
        "IRS_990T": "IRS-Form-990T",
        "UCC_FILING": "UCC-Filing",
        "SOS_FILING": "SOS-Filing",
        "CORPORATE_FILING": "Corporate-Filing",
        "MORTGAGE": "Mortgage",
        "COURT_FILING": "Court-Filing",
        "AUDITOR": "Audit-Report",
        "RECORDER_INSTRUMENT": "Recorder-Instrument",
        "FINANCIAL_STATEMENT": "Financial-Statement",
        "OTHER": "Document",
    }
    doc_label = _DOC_TYPE_LABELS.get(doc_type, "Document")

    # --- Sanitize entity name for filesystem ---
    # Replace spaces, commas, periods with hyphens; remove other special chars
    sanitized = _re.sub(r"[,\.\'\"]", "", entity)
    sanitized = _re.sub(r"\s+", "-", sanitized.strip())
    sanitized = _re.sub(r"[^A-Za-z0-9\-]", "", sanitized)
    # Collapse multiple hyphens
    sanitized = _re.sub(r"-{2,}", "-", sanitized)
    # Truncate to reasonable length
    sanitized = sanitized[:60].rstrip("-")

    if not sanitized:
        sanitized = "Unknown"

    return f"{date_str}_{sanitized}_{doc_label}{ext}"


def _extract_property_data(extracted_text, doc_type, document, case):
    """
    Extract property data from parcel records and deeds, creating/updating
    Property and PropertyTransaction model instances.

    For PARCEL_RECORD: Uses parse_auditor_parcel_card() to extract owner,
    valuation, sales history from county auditor PDF cards.

    For DEED: Uses parse_recorder_document() to extract grantor/grantee,
    consideration, and recording details from recorder deed PDFs.

    Property records are matched by parcel_number + case to avoid duplicates.
    This runs BEFORE signal detection so SR-003 (valuation anomaly) can fire.
    """
    from decimal import Decimal

    from .models import AuditAction, AuditLog, Property, PropertyTransaction

    if doc_type == "PARCEL_RECORD":
        from .entity_extraction import parse_auditor_parcel_card

        card = parse_auditor_parcel_card(extracted_text)
        if not card.parcel_number:
            return  # couldn't parse — nothing to save

        # Upsert Property by parcel_number within this case
        prop, created = Property.objects.update_or_create(
            case=case,
            parcel_number=card.parcel_number,
            defaults={
                "address": card.address or "",
                "county": card.county or "DARKE",
                "assessed_value": (
                    Decimal(str(card.current_assessed)) if card.current_assessed else None
                ),
                "purchase_price": (
                    Decimal(str(card.most_recent_sale_price))
                    if card.most_recent_sale_price
                    else None
                ),
                "notes": (
                    f"Owner: {card.owner or 'unknown'}\n"
                    f"Municipality: {card.municipality or ''}\n"
                    f"Township: {card.township or ''}\n"
                    f"Land Use: {card.land_use_code or ''}\n"
                    f"Acres: {card.acres or ''}\n"
                    f"Annual Tax: ${card.annual_tax or 0:,.2f}\n"
                    f"Foreclosure: {card.foreclosure or 'N'}\n"
                    f"Owner Occupied: {card.owner_occupied or 'N'}"
                ),
                "updated_at": timezone.now(),
            },
        )

        # Create PropertyTransaction records from sales history
        for sale in card.sales_history:
            if not sale.date:
                continue

            # Parse sale date
            sale_date = None
            try:
                parts = sale.date.split("/")
                if len(parts) == 3:
                    from datetime import date

                    sale_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass

            # Avoid duplicate transactions (same property + date + price)
            price = Decimal(str(sale.amount)) if sale.amount else None
            existing = PropertyTransaction.objects.filter(
                property=prop,
                transaction_date=sale_date,
                price=price,
            ).exists()

            if not existing:
                PropertyTransaction.objects.create(
                    property=prop,
                    document=document,
                    transaction_date=sale_date,
                    price=price,
                    notes=(
                        f"Buyer: {sale.buyer or 'unknown'}\n"
                        f"Seller: {sale.seller or 'unknown'}\n"
                        f"Deed Type: {sale.deed_type or 'unknown'}\n"
                        f"Book/Page: {sale.book or ''}/{sale.page or ''}\n"
                        f"Conveyance#: {sale.conveyance_number or ''}\n"
                        f"Valid: {sale.valid or 'UNKNOWN'}"
                    ),
                )

        AuditLog.log(
            action=AuditAction.DOCUMENT_INGESTED,
            table_name="properties",
            record_id=prop.pk,
            case_id=case.pk,
            after_state={
                "parcel_number": card.parcel_number,
                "owner": card.owner,
                "assessed_value": str(card.current_assessed),
                "purchase_price": str(card.most_recent_sale_price),
                "sales_count": len(card.sales_history),
                "source": "parcel_card_parser",
            },
        )

        logger.info(
            "property_extracted_parcel_card",
            extra={
                "document_id": str(document.pk),
                "property_id": str(prop.pk),
                "parcel_number": card.parcel_number,
                "created": created,
                "sales_extracted": len(card.sales_history),
                "valuations_extracted": len(card.valuation_history),
            },
        )

    elif doc_type == "DEED":
        from .county_recorder_connector import parse_recorder_document

        deed = parse_recorder_document(extracted_text)
        if not deed.parcel_id and not deed.grantee:
            return  # couldn't parse — nothing to save

        # For deeds, we may not have a parcel number — use grantee + case as fallback
        parcel_number = deed.parcel_id or ""

        if parcel_number:
            prop, created = Property.objects.update_or_create(
                case=case,
                parcel_number=parcel_number,
                defaults={
                    "county": deed.county if hasattr(deed, "county") and deed.county else "DARKE",
                    "purchase_price": (
                        Decimal(str(deed.consideration))
                        if deed.consideration and deed.consideration > 0
                        else None
                    ),
                    "notes": (
                        f"Grantor: {deed.grantor or 'unknown'}\n"
                        f"Grantee: {deed.grantee or 'unknown'}\n"
                        f"Instrument: {deed.instrument_type or 'unknown'}\n"
                        f"Book/Page: {deed.book_page or ''}\n"
                        f"Legal Description: {(deed.legal_description or '')[:200]}"
                    ),
                    "updated_at": timezone.now(),
                },
            )
        else:
            # No parcel — create a new Property with available info
            prop = Property.objects.create(
                case=case,
                parcel_number="",
                county="DARKE",
                purchase_price=(
                    Decimal(str(deed.consideration))
                    if deed.consideration and deed.consideration > 0
                    else None
                ),
                notes=(
                    f"Grantor: {deed.grantor or 'unknown'}\n"
                    f"Grantee: {deed.grantee or 'unknown'}\n"
                    f"Instrument: {deed.instrument_type or 'unknown'}\n"
                    f"Legal Description: {(deed.legal_description or '')[:200]}"
                ),
            )
            created = True

        # Create a PropertyTransaction for the deed
        recording_date = None
        if deed.recording_date:
            try:
                from datetime import date
                from datetime import datetime as _dt

                if isinstance(deed.recording_date, str):
                    recording_date = _dt.strptime(deed.recording_date, "%Y-%m-%d").date()
                elif isinstance(deed.recording_date, date):
                    recording_date = deed.recording_date
            except (ValueError, TypeError):
                pass

        price = (
            Decimal(str(deed.consideration))
            if deed.consideration and deed.consideration > 0
            else None
        )

        PropertyTransaction.objects.create(
            property=prop,
            document=document,
            transaction_date=recording_date,
            price=price,
            notes=(
                f"Grantor: {deed.grantor or 'unknown'}\n"
                f"Grantee: {deed.grantee or 'unknown'}\n"
                f"Instrument Type: {deed.instrument_type or ''}\n"
                f"Instrument#: {deed.instrument_number or ''}\n"
                f"Book/Page: {deed.book_page or ''}\n"
                f"Consideration Text: {deed.consideration_text or ''}"
            ),
        )

        AuditLog.log(
            action=AuditAction.DOCUMENT_INGESTED,
            table_name="properties",
            record_id=prop.pk,
            case_id=case.pk,
            after_state={
                "parcel_number": parcel_number,
                "grantor": deed.grantor,
                "grantee": deed.grantee,
                "consideration": str(deed.consideration),
                "instrument_type": deed.instrument_type,
                "source": "deed_parser",
            },
        )

        logger.info(
            "property_extracted_deed",
            extra={
                "document_id": str(document.pk),
                "property_id": str(prop.pk),
                "parcel_number": parcel_number,
                "created": created,
                "instrument_type": deed.instrument_type,
            },
        )


# ---------------------------------------------------------------------------
# Upload security constants — see SECURITY.md Rule 2
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "text/plain",
}


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails intake validation."""

    pass


def _validate_uploaded_file(uploaded_file):
    """Validate file size and MIME type before any processing.

    Raises UploadValidationError with a user-safe message on failure.
    See SECURITY.md Rule 2 and SEC-008/SEC-009.
    """
    # --- Size check ---
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise UploadValidationError(
            f"File '{uploaded_file.name}' is {uploaded_file.size:,} bytes, "
            f"which exceeds the {max_mb} MB limit."
        )

    # --- MIME type check ---
    content_type = getattr(uploaded_file, "content_type", None) or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise UploadValidationError(
            f"File type '{content_type}' is not allowed. "
            f"Accepted types: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
        )


def _process_uploaded_file(
    uploaded_file, case, doc_type_hint="OTHER", source_url=None, run_pipeline=True
):
    """Run the full upload pipeline for a single InMemoryUploadedFile.

    Returns the saved Document instance. Raises UploadValidationError for
    invalid files, and other exceptions for storage or DB errors.
    Entity extraction and signal detection failures are logged (best-effort).

    Security checks (see SECURITY.md Rule 2):
      1. File size validated against MAX_UPLOAD_SIZE_BYTES
      2. MIME type validated against ALLOWED_MIME_TYPES
      3. Filename sanitized to prevent path traversal (SEC-005)
      4. SHA-256 computed on original bytes before any processing
    """
    import hashlib as _hashlib
    import os as _os

    from django.core.files.storage import default_storage

    # --- Validate before touching the file (SEC-008, SEC-009) ---
    _validate_uploaded_file(uploaded_file)

    # --- SHA-256 on original bytes (SECURITY.md Rule 1) ---
    sha = _hashlib.sha256()
    for chunk in uploaded_file.chunks():
        sha.update(chunk)
    sha256 = sha.hexdigest()

    # --- Sanitize filename to prevent path traversal (SEC-005) ---
    safe_name = _os.path.basename(uploaded_file.name)
    if not safe_name:
        safe_name = f"unnamed_{sha256[:12]}"

    relative_path = f"cases/{case.pk}/{safe_name}"
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

    # --- PDF metadata extraction for chain-of-custody ---
    pdf_metadata = {}
    if uploaded_file.name.lower().endswith(".pdf"):
        try:
            from .extraction import extract_pdf_metadata

            abs_path = default_storage.path(saved_path)
            pdf_metadata = extract_pdf_metadata(abs_path)
            logger.info(
                "pdf_metadata_extracted",
                extra={
                    "doc_filename": safe_name,
                    "author": pdf_metadata.get("author", ""),
                    "creator": pdf_metadata.get("creator", ""),
                    "producer": pdf_metadata.get("producer", ""),
                    "page_count": pdf_metadata.get("page_count", 0),
                    "creation_date": pdf_metadata.get("creation_date", ""),
                },
            )
        except Exception:
            logger.warning("pdf_metadata_extraction_skipped", extra={"doc_filename": safe_name})

    doc_type = doc_type_hint
    auto_classified = False
    if run_pipeline and doc_type == "OTHER" and extracted_text:
        from .classification import classify_document

        doc_type = classify_document(extracted_text)
        auto_classified = True

    is_generated = auto_classified and doc_type == DocumentType.REFERRAL_MEMO

    # --- Build ingestion metadata record (chain-of-custody) ---
    ingestion_meta = {
        "original_filename": uploaded_file.name,
        "upload_size_bytes": uploaded_file.size,
        "sha256_at_ingest": sha256,
        "content_type": getattr(uploaded_file, "content_type", ""),
    }
    if pdf_metadata:
        ingestion_meta["pdf"] = pdf_metadata

    # --- Atomic DB writes: Document + AuditLog (SEC-012) ---
    # If either fails, both are rolled back. File is already stored on disk;
    # an orphaned file is detectable and recoverable (the reverse is worse).
    from django.db import transaction

    with transaction.atomic():
        document = Document.objects.create(
            case=case,
            filename=safe_name,
            file_path=saved_path,
            sha256_hash=sha256,
            file_size=uploaded_file.size,
            doc_type=doc_type,
            is_generated=is_generated,
            source_url=source_url or None,
            extracted_text=extracted_text or None,
            ocr_status=ocr_status,
            ingestion_metadata=ingestion_meta,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        # Audit log: document ingested (SEC-007)
        AuditLog.log(
            action=AuditAction.DOCUMENT_INGESTED,
            table_name="documents",
            record_id=document.pk,
            case_id=case.pk,
            sha256_hash=sha256,
            file_size=uploaded_file.size,
            after_state={"filename": safe_name, "doc_type": doc_type},
        )

    # --- SEC-027/028: Track extraction pipeline failures ---
    extraction_failures = []  # list of step names that failed
    entity_summary = None

    if run_pipeline and extracted_text and not is_generated:
        try:
            from .entity_extraction import extract_entities
            from .entity_resolution import resolve_all_entities

            # --- Stage 1a: Fast regex extraction (always runs) ---
            extraction_result = extract_entities(extracted_text, doc_type=doc_type)

            # --- Stage 1b: AI-enhanced extraction (best-effort) ---
            # Wraps Claude API call in try/except so regex results are never lost.
            # AI adds: deeper relationship extraction, better 990 parsing,
            # obituary family network mapping. Merged into extraction_result.
            try:
                from .ai_extraction import enhanced_extract

                use_ai = bool(_os.environ.get("ANTHROPIC_API_KEY"))
                if use_ai:
                    extraction_result = enhanced_extract(
                        extracted_text, doc_type=doc_type, use_ai=True
                    )
                    logger.info(
                        "ai_extraction_merged",
                        extra={
                            "document_id": str(document.pk),
                            "ai_proposals": (
                                extraction_result.get("meta", {}).get("ai_proposals", 0)
                            ),
                        },
                    )
            except Exception:
                logger.warning(
                    "ai_extraction_skipped",
                    extra={
                        "document_id": str(document.pk),
                        "reason": "AI extraction failed, using regex only",
                    },
                )

            # --- Stage 2: Data quality validation on extracted financials ---
            try:
                from .data_quality import validate_financial_snapshot as _vfs

                for fin in extraction_result.get("financials", []):
                    if fin.get("source") == "ai":
                        vr = _vfs(fin)
                        if not vr.is_clean:
                            logger.warning(
                                "ai_financial_quality_issues",
                                extra={
                                    "document_id": str(document.pk),
                                    "issues": [i.message for i in vr.issues[:5]],
                                },
                            )
            except Exception:
                logger.warning(
                    "data_quality_skipped",
                    extra={"document_id": str(document.pk)},
                )

            # --- Stage 3: Entity resolution (DB persistence) ---
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
            extraction_failures.append("entity_extraction")

    # Financial snapshot extraction for IRS 990 documents
    if run_pipeline and extracted_text and doc_type in ("IRS_990", "IRS_990T"):
        try:
            from .entity_extraction import extract_entities as _ee

            fin_result = _ee(extracted_text, doc_type=doc_type)
            financials = fin_result.get("financials", [])
            meta = fin_result.get("meta", {})
            if financials:
                _save_financial_snapshot(
                    document=document,
                    case=case,
                    financials=financials,
                    meta=meta,
                )
        except Exception:
            logger.exception(
                "financial_extraction_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )
            extraction_failures.append("financial_extraction")

    # Property extraction for parcel records and deeds
    if run_pipeline and extracted_text and doc_type in ("PARCEL_RECORD", "DEED"):
        try:
            _extract_property_data(
                extracted_text=extracted_text,
                doc_type=doc_type,
                document=document,
                case=case,
            )
        except Exception:
            logger.exception(
                "property_extraction_failed",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )
            extraction_failures.append("property_extraction")

    # Forensic filename generation — runs after entity extraction so we
    # have dates and entity names available for the canonical name.
    if run_pipeline and extracted_text and not is_generated:
        try:
            display_name = _generate_forensic_filename(
                doc_type=doc_type,
                extracted_text=extracted_text,
                original_filename=uploaded_file.name,
            )
            document.display_name = display_name

            # --- Physical file rename on disk ---
            # Rename the stored file to match the forensic canonical name.
            # Original filename is preserved in Document.filename and
            # ingestion_metadata for chain-of-custody. The SHA-256 hash
            # verifies the file hasn't been altered.
            try:
                old_abs = default_storage.path(saved_path)
                new_relative = f"cases/{case.pk}/{display_name}"
                new_abs = default_storage.path(new_relative)

                # Avoid collision: if forensic name already exists (rare),
                # append a short hash suffix
                if _os.path.exists(new_abs) and old_abs != new_abs:
                    stem, ext = _os.path.splitext(display_name)
                    new_relative = f"cases/{case.pk}/{stem}_{sha256[:8]}{ext}"
                    new_abs = default_storage.path(new_relative)

                if old_abs != new_abs:
                    _os.rename(old_abs, new_abs)
                    document.file_path = new_relative
                    logger.info(
                        "file_renamed_on_disk",
                        extra={
                            "document_id": str(document.pk),
                            "old_path": saved_path,
                            "new_path": new_relative,
                        },
                    )
            except Exception:
                logger.warning(
                    "file_rename_failed_display_only",
                    extra={
                        "document_id": str(document.pk),
                        "detail": "Display name set but physical file not renamed.",
                    },
                )

            document.save(update_fields=["display_name", "file_path"])
            logger.info(
                "forensic_filename_generated",
                extra={
                    "document_id": str(document.pk),
                    "original": uploaded_file.name,
                    "display_name": display_name,
                },
            )
        except Exception:
            logger.exception(
                "forensic_filename_failed",
                extra={"document_id": str(document.pk)},
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
            extraction_failures.append("signal_detection")

    # --- SEC-027/028: Persist extraction status on the document ---
    from .models import ExtractionStatus

    if not run_pipeline:
        ext_status = ExtractionStatus.PENDING
        ext_notes = ""
    elif not extracted_text and not is_generated:
        ext_status = ExtractionStatus.SKIPPED
        ext_notes = "No extracted text available for analysis."
    elif extraction_failures:
        if len(extraction_failures) >= 2:
            ext_status = ExtractionStatus.FAILED
        else:
            ext_status = ExtractionStatus.PARTIAL
        ext_notes = f"Failed steps: {', '.join(extraction_failures)}"
    else:
        ext_status = ExtractionStatus.COMPLETED
        ext_notes = ""

    document.extraction_status = ext_status
    document.extraction_notes = ext_notes
    document.save(update_fields=["extraction_status", "extraction_notes"])

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
            "extraction_status": ext_status,
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

    # Property extraction for parcel records and deeds
    if extracted_text and document.doc_type in ("PARCEL_RECORD", "DEED"):
        try:
            _extract_property_data(
                extracted_text=extracted_text,
                doc_type=document.doc_type,
                document=document,
                case=case,
            )
        except Exception:
            logger.exception(
                "property_extraction_failed_existing",
                extra={"document_id": str(document.pk), "case_id": str(case.pk)},
            )

    # Forensic filename generation for deferred-pipeline documents
    if extracted_text and not document.is_generated and not document.display_name:
        try:
            display_name = _generate_forensic_filename(
                doc_type=document.doc_type,
                extracted_text=extracted_text,
                original_filename=document.filename,
            )
            document.display_name = display_name
            document.save(update_fields=["display_name"])
            logger.info(
                "forensic_filename_generated_existing",
                extra={
                    "document_id": str(document.pk),
                    "original": document.filename,
                    "display_name": display_name,
                },
            )
        except Exception:
            logger.exception(
                "forensic_filename_failed_existing",
                extra={"document_id": str(document.pk)},
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


# ---------------------------------------------------------------------------
# SEC-024: CSRF cookie endpoint for SPA
# ---------------------------------------------------------------------------


@ensure_csrf_cookie
@require_http_methods(["GET"])
def api_csrf_token(request):
    """Return the CSRF token cookie to the frontend.

    The React SPA calls this once on startup so that subsequent write
    requests (POST/PATCH/DELETE) can include the token as X-CSRFToken.
    """
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Case collection & detail
# ---------------------------------------------------------------------------


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

    case = serializer.save()
    AuditLog.log(
        action=AuditAction.RECORD_CREATED,
        table_name="cases",
        record_id=case.pk,
        case_id=case.pk,
        after_state={"name": case.name, "status": case.status},
        performed_by=getattr(request, "api_token", None),
    )
    return JsonResponse(serializer.data, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_detail(request, pk):
    case = get_object_or_404(Case, pk=pk)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        before = {"status": case.status, "notes": case.notes, "referral_ref": case.referral_ref}
        serializer = CaseUpdateSerializer(data=payload, instance=case)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        AuditLog.log(
            action=AuditAction.RECORD_UPDATED,
            table_name="cases",
            record_id=case.pk,
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        case_id = case.pk
        case_name = case.name
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
        AuditLog.log(
            action=AuditAction.RECORD_DELETED,
            table_name="cases",
            record_id=case_id,
            case_id=case_id,
            before_state={"name": case_name},
            performed_by=getattr(request, "api_token", None),
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

        before = {"doc_type": document.doc_type, "doc_subtype": document.doc_subtype}
        serializer = DocumentUpdateSerializer(data=payload, instance=document)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        AuditLog.log(
            action=AuditAction.RECORD_UPDATED,
            table_name="documents",
            record_id=document.pk,
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            sha256_hash=document.sha256_hash,
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        doc_id = document.pk
        doc_hash = document.sha256_hash
        doc_filename = document.filename
        document.delete()
        AuditLog.log(
            action=AuditAction.DOCUMENT_DELETED,
            table_name="documents",
            record_id=doc_id,
            case_id=case.pk,
            sha256_hash=doc_hash,
            before_state={"filename": doc_filename},
            performed_by=getattr(request, "api_token", None),
        )
        return HttpResponse(status=204)

    # GET — return document with linked entities and financial data
    data = serialize_document(document)

    # Linked persons
    from .models import OrgDocument, PersonDocument

    person_links = PersonDocument.objects.filter(document=document).select_related("person")
    data["persons"] = [
        {
            "id": str(pl.person.pk),
            "full_name": pl.person.full_name,
            "role_tags": pl.person.role_tags or [],
            "address": pl.person.address,
            "phone": pl.person.phone,
            "context_note": pl.context_note or "",
        }
        for pl in person_links
    ]

    # Linked organizations
    org_links = OrgDocument.objects.filter(document=document).select_related("org")
    data["organizations"] = [
        {
            "id": str(ol.org.pk),
            "name": ol.org.name,
            "org_type": ol.org.org_type,
            "ein": ol.org.ein or "",
            "address": ol.org.address,
            "phone": ol.org.phone,
            "context_note": ol.context_note or "",
        }
        for ol in org_links
    ]

    # Financial snapshots (for 990s)
    from .models import FinancialSnapshot

    snapshots = FinancialSnapshot.objects.filter(document=document).order_by("tax_year")
    data["financial_snapshots"] = [
        {
            "id": str(s.pk),
            "tax_year": s.tax_year,
            "ein": s.ein,
            "total_contributions": s.total_contributions,
            "program_service_revenue": s.program_service_revenue,
            "investment_income": s.investment_income,
            "other_revenue": s.other_revenue,
            "total_revenue": s.total_revenue,
            "grants_paid": s.grants_paid,
            "salaries_and_compensation": s.salaries_and_compensation,
            "professional_fundraising": s.professional_fundraising,
            "other_expenses": s.other_expenses,
            "total_expenses": s.total_expenses,
            "revenue_less_expenses": s.revenue_less_expenses,
            "total_assets_boy": s.total_assets_boy,
            "total_assets_eoy": s.total_assets_eoy,
            "total_liabilities_boy": s.total_liabilities_boy,
            "total_liabilities_eoy": s.total_liabilities_eoy,
            "net_assets_boy": s.net_assets_boy,
            "net_assets_eoy": s.net_assets_eoy,
            "officer_compensation_total": s.officer_compensation_total,
            "num_employees": s.num_employees,
            "source": s.source,
            "confidence": s.confidence,
        }
        for s in snapshots
    ]

    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Financials API endpoint — year-over-year view
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_case_financials(request, pk):
    """Return all FinancialSnapshot records for a case, ordered by tax_year."""
    from .models import FinancialSnapshot

    case = get_object_or_404(Case, pk=pk)
    snapshots = (
        FinancialSnapshot.objects.filter(case=case)
        .select_related("document", "organization")
        .order_by("tax_year")
    )

    results = []
    for s in snapshots:
        row = {
            "id": str(s.pk),
            "document_id": str(s.document_id),
            "document_filename": s.document.filename if s.document else None,
            "organization_id": str(s.organization_id) if s.organization_id else None,
            "organization_name": s.organization.name if s.organization else None,
            "ein": s.ein,
            "tax_year": s.tax_year,
            "form_type": s.form_type,
            "total_contributions": s.total_contributions,
            "program_service_revenue": s.program_service_revenue,
            "investment_income": s.investment_income,
            "other_revenue": s.other_revenue,
            "total_revenue": s.total_revenue,
            "grants_paid": s.grants_paid,
            "salaries_and_compensation": s.salaries_and_compensation,
            "professional_fundraising": s.professional_fundraising,
            "other_expenses": s.other_expenses,
            "total_expenses": s.total_expenses,
            "revenue_less_expenses": s.revenue_less_expenses,
            "total_assets_boy": s.total_assets_boy,
            "total_assets_eoy": s.total_assets_eoy,
            "total_liabilities_boy": s.total_liabilities_boy,
            "total_liabilities_eoy": s.total_liabilities_eoy,
            "net_assets_boy": s.net_assets_boy,
            "net_assets_eoy": s.net_assets_eoy,
            "officer_compensation_total": s.officer_compensation_total,
            "num_employees": s.num_employees,
            "source": s.source,
            "confidence": s.confidence,
        }
        results.append(row)

    # Compute YoY deltas
    for i in range(1, len(results)):
        prev, curr = results[i - 1], results[i]
        for field in ["total_revenue", "total_expenses", "total_assets_eoy", "net_assets_eoy"]:
            pv, cv = prev.get(field), curr.get(field)
            if pv and cv and pv != 0:
                curr[f"{field}_yoy_pct"] = round((cv - pv) / abs(pv) * 100, 1)

    return JsonResponse({"count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Signal API endpoints
# ---------------------------------------------------------------------------

SIGNAL_SORT_FIELDS = {"detected_at", "severity", "status", "rule_id", "id"}


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

        before = {"status": signal.status, "investigator_note": signal.investigator_note}
        serializer = SignalUpdateSerializer(data=payload, instance=signal)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()

        # Determine the right audit action based on the new status
        new_status = serializer.validated_data.get("status", signal.status)
        if new_status == "CONFIRMED":
            audit_action = AuditAction.SIGNAL_CONFIRMED
        elif new_status == "DISMISSED":
            audit_action = AuditAction.SIGNAL_DISMISSED
        elif new_status == "ESCALATED":
            audit_action = AuditAction.SIGNAL_ESCALATED
        else:
            audit_action = AuditAction.RECORD_UPDATED

        AuditLog.log(
            action=audit_action,
            table_name="signals",
            record_id=signal.pk,
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
        )

        # Auto-escalate: when a signal is CONFIRMED, create a Detection
        # per the charter workflow: Signal → Detection → Finding
        detection_data = None
        if new_status == "CONFIRMED":
            try:
                from .signal_rules import escalate_signal_to_detection

                note = serializer.validated_data.get("investigator_note", "")
                detection = escalate_signal_to_detection(signal, investigator_note=note)
                detection_data = serialize_detection(detection)

                AuditLog.log(
                    action=AuditAction.RECORD_CREATED,
                    table_name="detections",
                    record_id=detection.pk,
                    case_id=case.pk,
                    after_state={
                        "escalated_from_signal": str(signal.pk),
                        "rule_id": signal.rule_id,
                    },
                    performed_by=getattr(request, "api_token", None),
                    notes="signal_escalated_to_detection",
                )
            except Exception:
                logger.exception(
                    "signal_escalation_failed",
                    extra={"signal_id": str(signal.pk), "case_id": str(case.pk)},
                )

        response_data = serializer.data
        if detection_data:
            response_data["created_detection"] = detection_data
        return JsonResponse(response_data)

    return JsonResponse(serialize_signal(signal))


_SEVERITY_RANK = {
    SignalSeverity.CRITICAL: 4,
    SignalSeverity.HIGH: 3,
    SignalSeverity.MEDIUM: 2,
    SignalSeverity.LOW: 1,
}

_RANK_TO_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}


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

    from django.db.models import Count

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


# ---------------------------------------------------------------------------
# Full-text search across all entities
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_search(request):
    """Full-text search across cases, documents, signals, and entities.

    Uses PostgreSQL full-text search with ``SearchVector`` / ``SearchQuery``
    and ``SearchRank`` so that results are ranked by relevance rather than
    relying on simple ``__icontains`` substring matching.

    Query params:
        q        — search term (required, min 2 chars)
        type     — filter to one type: case, document, signal, entity
        case_id  — restrict results to a specific case

    TODO(SEC-010): When user-level auth is added, scope all sub-queries to
    cases the authenticated user has access to.
    """
    raw_query = request.GET.get("q", "").strip()
    if len(raw_query) < 2:
        return JsonResponse(
            {"errors": {"q": ["Search query must be at least 2 characters."]}},
            status=400,
        )

    raw_type = request.GET.get("type")
    raw_case_id = request.GET.get("case_id")

    valid_types = {"case", "document", "signal", "entity"}
    if raw_type and raw_type not in valid_types:
        return JsonResponse(
            {
                "errors": {
                    "type": [f"Invalid type. Expected one of: {', '.join(sorted(valid_types))}."]
                }
            },
            status=400,
        )

    # Build a PostgreSQL full-text SearchQuery.  We use 'plain' mode so
    # the user can type natural phrases and each word is AND-ed together.
    search_query = SearchQuery(raw_query, search_type="plain")

    results = []

    # --- Cases ---
    if raw_type in (None, "case"):
        vector = SearchVector("name", weight="A") + SearchVector("notes", weight="B")
        case_qs = (
            Case.objects.annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            case_qs = case_qs.filter(pk=raw_case_id)
        for c in case_qs[:25]:
            results.append(
                {
                    "type": "case",
                    "id": str(c.pk),
                    "title": c.name,
                    "subtitle": f"Status: {c.status}",
                    "snippet": f"Status: {c.status}" + (f" — {c.notes[:120]}" if c.notes else ""),
                    "relevance": round(float(c.rank), 4),
                    "case_id": str(c.pk),
                    "case_name": c.name,
                    "route": f"/cases/{c.pk}",
                }
            )

    # --- Documents ---
    if raw_type in (None, "document"):
        vector = SearchVector("filename", weight="A") + SearchVector("extracted_text", weight="B")
        doc_qs = (
            Document.objects.select_related("case")
            .annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            doc_qs = doc_qs.filter(case_id=raw_case_id)
        for d in doc_qs[:25]:
            # Build a snippet showing the match context
            snippet = d.filename
            if d.extracted_text and raw_query.lower() in d.extracted_text.lower():
                idx = d.extracted_text.lower().index(raw_query.lower())
                start = max(0, idx - 60)
                end = min(len(d.extracted_text), idx + len(raw_query) + 60)
                snippet = (
                    ("..." if start > 0 else "")
                    + d.extracted_text[start:end].strip()
                    + ("..." if end < len(d.extracted_text) else "")
                )
            results.append(
                {
                    "type": "document",
                    "id": str(d.pk),
                    "title": d.filename,
                    "subtitle": f"{d.doc_type} — {d.case.name}",
                    "snippet": snippet,
                    "relevance": round(float(d.rank), 4),
                    "case_id": str(d.case_id),
                    "case_name": d.case.name,
                    "route": f"/cases/{d.case_id}",
                }
            )

    # --- Signals ---
    if raw_type in (None, "signal"):
        vector = SearchVector("detected_summary", weight="A")
        sig_qs = (
            Signal.objects.select_related("case")
            .annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            sig_qs = sig_qs.filter(case_id=raw_case_id)
        for s in sig_qs[:25]:
            results.append(
                {
                    "type": "signal",
                    "id": str(s.pk),
                    "title": f"{s.rule_id} — {s.severity}",
                    "subtitle": f"Signal — {s.status}",
                    "snippet": s.detected_summary[:200] if s.detected_summary else "",
                    "relevance": round(float(s.rank), 4),
                    "case_id": str(s.case_id),
                    "case_name": s.case.name,
                    "route": f"/cases/{s.case_id}",
                }
            )

    # --- Entities (persons, orgs, properties, financial instruments) ---
    if raw_type in (None, "entity"):
        # Persons — search full_name and notes
        p_vector = SearchVector("full_name", weight="A") + SearchVector("notes", weight="C")
        person_qs = (
            Person.objects.select_related("case")
            .annotate(rank=SearchRank(p_vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            person_qs = person_qs.filter(case_id=raw_case_id)
        for p in person_qs[:25]:
            results.append(
                {
                    "type": "entity",
                    "id": str(p.pk),
                    "title": p.full_name,
                    "subtitle": "Person" + (f" — {', '.join(p.role_tags)}" if p.role_tags else ""),
                    "snippet": f"Person — Roles: {', '.join(p.role_tags)}"
                    if p.role_tags
                    else "Person",
                    "relevance": round(float(p.rank), 4),
                    "case_id": str(p.case_id),
                    "case_name": p.case.name,
                    "route": f"/entities/person/{p.pk}",
                }
            )

        # Organizations — search name and notes
        o_vector = SearchVector("name", weight="A") + SearchVector("notes", weight="C")
        org_qs = (
            Organization.objects.select_related("case")
            .annotate(rank=SearchRank(o_vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            org_qs = org_qs.filter(case_id=raw_case_id)
        for o in org_qs[:25]:
            results.append(
                {
                    "type": "entity",
                    "id": str(o.pk),
                    "title": o.name,
                    "subtitle": f"Organization — {o.org_type}",
                    "snippet": f"Organization — {o.org_type}"
                    + (f", EIN: {o.ein}" if o.ein else ""),
                    "relevance": round(float(o.rank), 4),
                    "case_id": str(o.case_id),
                    "case_name": o.case.name,
                    "route": f"/entities/organization/{o.pk}",
                }
            )

        # Properties — search address, parcel_number, county
        prop_vector = (
            SearchVector("address", weight="A")
            + SearchVector("parcel_number", weight="B")
            + SearchVector("county", weight="C")
        )
        prop_qs = (
            Property.objects.select_related("case")
            .annotate(rank=SearchRank(prop_vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            prop_qs = prop_qs.filter(case_id=raw_case_id)
        for p in prop_qs[:25]:
            results.append(
                {
                    "type": "entity",
                    "id": str(p.pk),
                    "title": p.address or p.parcel_number or str(p.pk)[:8],
                    "subtitle": f"Property — {p.county or 'Unknown'} County",
                    "snippet": (
                        f"Property — {p.county or 'Unknown'} County"
                        + (f", Parcel: {p.parcel_number}" if p.parcel_number else "")
                    ),
                    "relevance": round(float(p.rank), 4),
                    "case_id": str(p.case_id),
                    "case_name": p.case.name,
                    "route": f"/entities/property/{p.pk}",
                }
            )

        # Financial Instruments — search filing_number and instrument_type
        fi_vector = SearchVector("filing_number", weight="A") + SearchVector(
            "instrument_type", weight="B"
        )
        fi_qs = (
            FinancialInstrument.objects.select_related("case")
            .annotate(rank=SearchRank(fi_vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )
        if raw_case_id:
            fi_qs = fi_qs.filter(case_id=raw_case_id)
        for fi in fi_qs[:25]:
            results.append(
                {
                    "type": "entity",
                    "id": str(fi.pk),
                    "title": f"{fi.instrument_type} {fi.filing_number or ''}".strip(),
                    "subtitle": f"Financial Instrument — {fi.instrument_type}",
                    "snippet": f"Financial Instrument — {fi.instrument_type}",
                    "relevance": round(float(fi.rank), 4),
                    "case_id": str(fi.case_id),
                    "case_name": fi.case.name,
                    "route": f"/entities/financial_instrument/{fi.pk}",
                }
            )

    # Sort by relevance descending, then alphabetically by title
    results.sort(key=lambda r: (-r["relevance"], r["title"]))

    return JsonResponse(
        {
            "query": raw_query,
            "total": len(results),
            "ai_overview": "",
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Case export
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_case_export(request, pk):
    """Export all case data as JSON or CSV.

    Query params:
        format — 'json' (default) or 'csv'
    """
    case = get_object_or_404(Case, pk=pk)
    export_format = request.GET.get("format", "json").lower()

    if export_format not in ("json", "csv"):
        return JsonResponse(
            {"errors": {"format": ["Invalid format. Expected 'json' or 'csv'."]}},
            status=400,
        )

    # Gather all related data
    documents = list(case.documents.order_by("-uploaded_at"))
    signals = list(case.signals.order_by("-detected_at"))
    detections = list(case.detections.order_by("-detected_at"))
    findings = list(Finding.objects.filter(case=case).order_by("-created_at"))
    referrals = list(case.referrals.order_by("-filing_date"))
    persons = list(case.persons.order_by("full_name"))
    organizations = list(case.organizations.order_by("name"))
    properties = list(case.properties.order_by("-created_at"))
    financial_instruments = list(case.financial_instruments.order_by("-created_at"))

    import json as json_mod
    import os

    from django.conf import settings

    # Ensure exports directory exists under MEDIA_ROOT
    exports_dir = os.path.join(settings.MEDIA_ROOT, "exports")
    os.makedirs(exports_dir, exist_ok=True)

    if export_format == "json":
        export_data = {
            "case": serialize_case(case),
            "documents": [serialize_document(d) for d in documents],
            "signals": [serialize_signal(s) for s in signals],
            "detections": [serialize_detection(d) for d in detections],
            "findings": [
                {
                    "id": str(f.pk),
                    "title": f.title,
                    "narrative": f.narrative,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "status": f.status,
                    "signal_type": f.signal_type,
                    "signal_rule_id": f.signal_rule_id,
                    "legal_refs": f.legal_refs,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in findings
            ],
            "referrals": [serialize_referral(r) for r in referrals],
            "persons": [serialize_person(p) for p in persons],
            "organizations": [serialize_organization(o) for o in organizations],
            "properties": [serialize_property(p) for p in properties],
            "financial_instruments": [
                serialize_financial_instrument(fi) for fi in financial_instruments
            ],
            "exported_at": timezone.now().isoformat(),
        }

        filename = f"catalyst_case_{case.pk}.json"
        filepath = os.path.join(exports_dir, filename)
        with open(filepath, "w") as fh:
            json_mod.dump(export_data, fh, indent=2)

        download_url = f"/{settings.MEDIA_URL}exports/{filename}"
        return JsonResponse(
            {
                "format": "json",
                "filename": filename,
                "download_url": download_url,
            }
        )

    # CSV export — one section per entity type, separated by headers
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Case summary
    writer.writerow(["=== CASE SUMMARY ==="])
    writer.writerow(["ID", "Name", "Status", "Notes", "Referral Ref", "Created At"])
    writer.writerow(
        [
            str(case.pk),
            case.name,
            case.status,
            case.notes or "",
            case.referral_ref or "",
            case.created_at.isoformat() if case.created_at else "",
        ]
    )
    writer.writerow([])

    # Documents
    writer.writerow(["=== DOCUMENTS ==="])
    writer.writerow(["ID", "Filename", "Doc Type", "File Size", "OCR Status", "Uploaded At"])
    for d in documents:
        writer.writerow(
            [
                str(d.pk),
                d.filename,
                d.doc_type,
                d.file_size,
                d.ocr_status,
                d.uploaded_at.isoformat() if d.uploaded_at else "",
            ]
        )
    writer.writerow([])

    # Signals
    writer.writerow(["=== SIGNALS ==="])
    writer.writerow(["ID", "Rule ID", "Severity", "Status", "Summary", "Detected At"])
    for s in signals:
        writer.writerow(
            [
                str(s.pk),
                s.rule_id,
                s.severity,
                s.status,
                s.detected_summary or "",
                s.detected_at.isoformat() if s.detected_at else "",
            ]
        )
    writer.writerow([])

    # Persons
    writer.writerow(["=== PERSONS ==="])
    writer.writerow(["ID", "Full Name", "Aliases", "Role Tags", "Date of Death", "Notes"])
    for p in persons:
        writer.writerow(
            [
                str(p.pk),
                p.full_name,
                "; ".join(p.aliases),
                "; ".join(p.role_tags),
                p.date_of_death or "",
                p.notes or "",
            ]
        )
    writer.writerow([])

    # Organizations
    writer.writerow(["=== ORGANIZATIONS ==="])
    writer.writerow(["ID", "Name", "Type", "EIN", "State", "Status", "Formation Date"])
    for o in organizations:
        writer.writerow(
            [
                str(o.pk),
                o.name,
                o.org_type,
                o.ein or "",
                o.registration_state or "",
                o.status,
                o.formation_date or "",
            ]
        )
    writer.writerow([])

    # Properties
    writer.writerow(["=== PROPERTIES ==="])
    writer.writerow(
        ["ID", "Parcel Number", "Address", "County", "Assessed Value", "Purchase Price"]
    )
    for p in properties:
        writer.writerow(
            [
                str(p.pk),
                p.parcel_number or "",
                p.address or "",
                p.county or "",
                str(p.assessed_value) if p.assessed_value else "",
                str(p.purchase_price) if p.purchase_price else "",
            ]
        )
    writer.writerow([])

    # Financial Instruments
    writer.writerow(["=== FINANCIAL INSTRUMENTS ==="])
    writer.writerow(["ID", "Type", "Filing Number", "Filing Date", "Amount", "Anomaly Flags"])
    for fi in financial_instruments:
        writer.writerow(
            [
                str(fi.pk),
                fi.instrument_type,
                fi.filing_number or "",
                fi.filing_date or "",
                str(fi.amount) if fi.amount else "",
                "; ".join(fi.anomaly_flags),
            ]
        )
    writer.writerow([])

    # Referrals
    writer.writerow(["=== REFERRALS ==="])
    writer.writerow(["ID", "Agency", "Status", "Submission ID", "Filing Date", "Notes"])
    for r in referrals:
        writer.writerow(
            [
                r.referral_id,
                r.agency_name or "",
                r.status,
                r.submission_id or "",
                r.filing_date.isoformat() if r.filing_date else "",
                r.notes or "",
            ]
        )

    filename = f"catalyst_case_{case.pk}.csv"
    filepath = os.path.join(exports_dir, filename)
    with open(filepath, "w") as fh:
        fh.write(output.getvalue())

    download_url = f"/{settings.MEDIA_URL}exports/{filename}"
    return JsonResponse(
        {
            "format": "csv",
            "filename": filename,
            "download_url": download_url,
        }
    )


# ---------------------------------------------------------------------------
# Entity detail (single entity with related data)
# ---------------------------------------------------------------------------

ENTITY_TYPE_MAP = {
    "person": (Person, serialize_person),
    "organization": (Organization, serialize_organization),
    "property": (Property, serialize_property),
    "financial_instrument": (FinancialInstrument, serialize_financial_instrument),
}


@require_http_methods(["GET"])
def api_entity_detail(request, entity_type, entity_id):
    """Return a single entity with its full related data.

    URL: /api/entities/<type>/<uuid>/
    Where type is: person, organization, property, financial_instrument
    """
    if entity_type not in ENTITY_TYPE_MAP:
        return JsonResponse(
            {
                "errors": {
                    "entity_type": [
                        f"Invalid entity type. Expected one of: "
                        f"{', '.join(sorted(ENTITY_TYPE_MAP.keys()))}."
                    ]
                }
            },
            status=400,
        )

    model_class, serializer_fn = ENTITY_TYPE_MAP[entity_type]
    entity = get_object_or_404(model_class, pk=entity_id)

    # Base entity data
    data = serializer_fn(entity)

    # Attach the parent case name
    data["case_name"] = entity.case.name

    # --- Related Documents (via junction tables) ---
    related_docs = []
    if entity_type == "person":
        for pd in PersonDocument.objects.filter(person=entity).select_related("document"):
            doc_data = serialize_document(pd.document)
            doc_data["page_reference"] = pd.page_reference
            doc_data["context_note"] = pd.context_note
            related_docs.append(doc_data)
    elif entity_type == "organization":
        for od in OrgDocument.objects.filter(org=entity).select_related("document"):
            doc_data = serialize_document(od.document)
            doc_data["page_reference"] = od.page_reference
            doc_data["context_note"] = od.context_note
            related_docs.append(doc_data)
    data["related_documents"] = related_docs

    # --- Related Signals (via EntitySignal) ---
    entity_signal_links = EntitySignal.objects.filter(
        entity_id=entity_id, entity_type=entity_type
    ).select_related("signal")
    data["related_signals"] = [serialize_signal(es.signal) for es in entity_signal_links]

    # --- Related Findings (via FindingEntity) ---
    finding_links = FindingEntity.objects.filter(
        entity_id=entity_id, entity_type=entity_type
    ).select_related("finding")
    data["related_findings"] = [
        {
            "id": str(fe.finding.pk),
            "title": fe.finding.title,
            "severity": fe.finding.severity,
            "status": fe.finding.status,
            "context_note": fe.context_note,
        }
        for fe in finding_links
    ]

    # --- Type-specific relationships ---
    if entity_type == "person":
        org_roles = PersonOrganization.objects.filter(person=entity).select_related("org")
        data["organization_roles"] = [
            {
                "organization_id": str(por.org_id),
                "organization_name": por.org.name,
                "role": por.role,
                "start_date": por.start_date.isoformat() if por.start_date else None,
                "end_date": por.end_date.isoformat() if por.end_date else None,
                "notes": por.notes or "",
            }
            for por in org_roles
        ]
    elif entity_type == "property":
        transactions = PropertyTransaction.objects.filter(property=entity).select_related(
            "document"
        )
        data["transactions"] = [
            {
                "id": str(pt.pk),
                "transaction_date": (
                    pt.transaction_date.isoformat() if pt.transaction_date else None
                ),
                "buyer_id": str(pt.buyer_id) if pt.buyer_id else None,
                "seller_id": str(pt.seller_id) if pt.seller_id else None,
                "price": str(pt.price) if pt.price else None,
                "document_id": str(pt.document_id) if pt.document_id else None,
                "notes": pt.notes or "",
            }
            for pt in transactions
        ]

    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Finding CRUD
# ---------------------------------------------------------------------------

FINDING_SORT_FIELDS = {
    "created_at",
    "updated_at",
    "severity",
    "confidence",
    "status",
    "title",
    "id",
}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_case_finding_collection(request, pk):
    """List or create findings for a case.

    GET query params:
        status      — filter by status (e.g. DRAFT, REVIEWED)
        severity    — filter by severity
        order_by    — sort field (default: created_at)
        direction   — asc or desc (default: desc)
        limit       — page size (default 25, max 100)
        offset      — pagination offset
    """
    case = get_object_or_404(Case, pk=pk)

    if request.method == "GET":
        qs = Finding.objects.filter(case=case).prefetch_related(
            "entity_links",
            "document_links",
        )

        # Filters
        if status := request.GET.get("status"):
            qs = qs.filter(status=status)
        if severity := request.GET.get("severity"):
            qs = qs.filter(severity=severity)
        if signal_type := request.GET.get("signal_type"):
            qs = qs.filter(signal_type=signal_type)

        # Sorting
        order_by, direction, sort_error = _parse_sort_params(
            request,
            allowed_fields=FINDING_SORT_FIELDS,
            default_field="created_at",
        )
        if sort_error is not None:
            return sort_error
        qs = qs.order_by(*_build_ordering_fields(order_by, direction))

        # Pagination
        limit, offset, err = _parse_limit_offset(request)
        if err:
            return err
        total = qs.count()
        page = qs[offset : offset + limit]

        return JsonResponse(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "previous_offset": max(0, offset - limit) if offset > 0 else None,
                "results": [serialize_finding(f) for f in page],
            }
        )

    # POST — create a new finding
    payload, err = _parse_json_body(request)
    if err:
        return err

    serializer = FindingIntakeSerializer(data=payload, case=case)
    if not serializer.is_valid():
        return JsonResponse({"errors": serializer.errors}, status=400)

    finding = serializer.save()
    AuditLog.log(
        action=AuditAction.FINDING_CREATED,
        table_name="findings",
        record_id=finding.pk,
        case_id=case.pk,
        after_state={
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
        },
        performed_by=getattr(request, "api_token", None),
    )
    return JsonResponse(serialize_finding(finding), status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_finding_detail(request, pk, finding_id):
    """Retrieve, update, or delete a single finding within a case."""
    case = get_object_or_404(Case, pk=pk)
    finding = get_object_or_404(
        Finding.objects.prefetch_related("entity_links", "document_links"),
        pk=finding_id,
        case=case,
    )

    if request.method == "GET":
        return JsonResponse(serialize_finding(finding))

    if request.method == "DELETE":
        finding_id = finding.pk
        finding_title = finding.title
        finding.delete()
        AuditLog.log(
            action=AuditAction.RECORD_DELETED,
            table_name="findings",
            record_id=finding_id,
            case_id=case.pk,
            before_state={"title": finding_title},
            performed_by=getattr(request, "api_token", None),
        )
        return HttpResponse(status=204)

    # PATCH
    payload, err = _parse_json_body(request)
    if err:
        return err

    before = {"title": finding.title, "severity": finding.severity, "status": finding.status}
    serializer = FindingUpdateSerializer(data=payload, instance=finding)
    if not serializer.is_valid():
        return JsonResponse({"errors": serializer.errors}, status=400)

    updated = serializer.save()
    AuditLog.log(
        action=AuditAction.FINDING_UPDATED,
        table_name="findings",
        record_id=updated.pk,
        case_id=case.pk,
        before_state=before,
        after_state=serializer.validated_data,
        performed_by=getattr(request, "api_token", None),
    )
    return JsonResponse(serialize_finding(updated))


# ---------------------------------------------------------------------------
# Investigator Notes CRUD
# ---------------------------------------------------------------------------

NOTE_SORT_FIELDS = {"created_at", "updated_at", "target_type", "id"}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_case_note_collection(request, pk):
    """List or create investigator notes for a case.

    GET query params:
        target_type — filter by target type (e.g. 'document', 'signal')
        target_id   — filter by specific target
        limit/offset — pagination
    """
    case = get_object_or_404(Case, pk=pk)

    if request.method == "POST":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        serializer = NoteIntakeSerializer(data=payload, case=case)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        note = serializer.save()
        AuditLog.log(
            action=AuditAction.RECORD_CREATED,
            table_name="investigator_notes",
            record_id=note.pk,
            case_id=case.pk,
            after_state={"target_type": note.target_type, "target_id": str(note.target_id)},
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data, status=201)

    # GET
    limit, offset, pagination_error = _parse_limit_offset(request)
    if pagination_error is not None:
        return pagination_error

    order_by, direction, sort_error = _parse_sort_params(
        request,
        allowed_fields=NOTE_SORT_FIELDS,
        default_field="created_at",
    )
    if sort_error is not None:
        return sort_error

    ordering = _build_ordering_fields(order_by, direction)
    qs = InvestigatorNote.objects.filter(case=case).order_by(*ordering)

    raw_target_type = request.GET.get("target_type")
    if raw_target_type is not None:
        qs = qs.filter(target_type=raw_target_type)

    raw_target_id = request.GET.get("target_id")
    if raw_target_id is not None:
        qs = qs.filter(target_id=raw_target_id)

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
            "results": [serialize_note(n) for n in paged],
        }
    )


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_note_detail(request, pk, note_id):
    """Get, update, or delete a single investigator note."""
    case = get_object_or_404(Case, pk=pk)
    note = get_object_or_404(InvestigatorNote, pk=note_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        before = {"content": note.content}
        serializer = NoteUpdateSerializer(data=payload, instance=note)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()
        AuditLog.log(
            action=AuditAction.RECORD_UPDATED,
            table_name="investigator_notes",
            record_id=note.pk,
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        note_id = note.pk
        note.delete()
        AuditLog.log(
            action=AuditAction.RECORD_DELETED,
            table_name="investigator_notes",
            record_id=note_id,
            case_id=case.pk,
            performed_by=getattr(request, "api_token", None),
        )
        return HttpResponse(status=204)

    return JsonResponse(serialize_note(note))


# ---------------------------------------------------------------------------
# Cross-case signals list
# ---------------------------------------------------------------------------

SIGNAL_SORT_FIELDS = {"detected_at", "severity", "status", "rule_id", "id"}


@require_http_methods(["GET"])
def api_signal_collection(request):
    """Cross-case signal list with filters.

    TODO(SEC-010): When user-level auth is added, scope this queryset to
    cases the authenticated user has access to, e.g.:
        qs = qs.filter(case__in=request.user.accessible_cases)
    """
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
    qs = Signal.objects.select_related("case").order_by(*ordering)

    # Filters
    raw_status = request.GET.get("status")
    if raw_status is not None:
        qs = qs.filter(status=raw_status)

    raw_severity = request.GET.get("severity")
    if raw_severity is not None:
        qs = qs.filter(severity=raw_severity)

    raw_case_id = request.GET.get("case_id")
    if raw_case_id is not None:
        qs = qs.filter(case_id=raw_case_id)

    raw_rule_id = request.GET.get("rule_id")
    if raw_rule_id is not None:
        qs = qs.filter(rule_id=raw_rule_id)

    total_count = qs.count()
    paged = qs[offset : offset + limit]
    next_offset = offset + limit if (offset + limit) < total_count else None
    previous_offset = max(offset - limit, 0) if offset > 0 else None

    results = []
    for signal in paged:
        data = serialize_signal(signal)
        data["case_name"] = signal.case.name
        results.append(data)

    return JsonResponse(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "previous_offset": previous_offset,
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Cross-case referrals list
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_referral_collection(request):
    """Cross-case referral list with filters.

    TODO(SEC-010): When user-level auth is added, scope this queryset to
    cases the authenticated user has access to.
    """
    limit, offset, pagination_error = _parse_limit_offset(request)
    if pagination_error is not None:
        return pagination_error

    qs = GovernmentReferral.objects.select_related("case").order_by("-filing_date")

    raw_status = request.GET.get("status")
    if raw_status is not None:
        qs = qs.filter(status=raw_status)

    raw_agency = request.GET.get("agency")
    if raw_agency is not None:
        qs = qs.filter(agency_name__icontains=raw_agency)

    raw_case_id = request.GET.get("case_id")
    if raw_case_id is not None:
        qs = qs.filter(case_id=raw_case_id)

    total_count = qs.count()
    paged = qs[offset : offset + limit]
    next_offset = offset + limit if (offset + limit) < total_count else None
    previous_offset = max(offset - limit, 0) if offset > 0 else None

    results = []
    for referral in paged:
        data = serialize_referral(referral)
        data["case_name"] = referral.case.name if referral.case else ""
        results.append(data)

    return JsonResponse(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "previous_offset": previous_offset,
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Case entity-relationship graph (Phase 2A)
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_case_graph(request, pk):
    """Return all entities + relationships for a case as a graph structure.

    Response shape:
        {
            "nodes": [{ "id", "type", "label", "metadata": {...} }, ...],
            "edges": [
                { "source", "target", "relationship", "label", "weight",
                  "metadata": {...} }, ...
            ],
            "stats": { "total_nodes", "total_edges", "node_types": {...} }
        }

    Nodes are derived from Person, Organization, Property, FinancialInstrument.
    Edges are derived from PersonOrganization, PersonDocument, OrgDocument,
    PropertyTransaction, Relationship, and SocialMediaConnection junction tables.
    """
    case = get_object_or_404(Case, pk=pk)

    nodes = []  # list of node dicts
    edges = []  # list of edge dicts
    node_ids = set()  # track which UUIDs are in the graph
    node_type_counts = {"person": 0, "organization": 0, "property": 0, "financial_instrument": 0}

    # ── Helper: build signal count lookup per entity ──────────────────
    # EntitySignal stores (signal_id, entity_id, entity_type) so we group
    # by entity_id to get how many signals reference each entity.
    entity_signal_counts = {}
    for row in (
        EntitySignal.objects.filter(signal__case=case).values("entity_id").annotate(cnt=Count("id"))
    ):
        entity_signal_counts[str(row["entity_id"])] = row["cnt"]

    # ── Helper: build detection count lookups per entity ──────────────
    # Detection has direct FK fields: person, organization, property_record,
    # financial_instrument. We count per-entity for each type.
    _det_person_counts = {}
    for row in (
        Detection.objects.filter(case=case, person__isnull=False)
        .values("person_id")
        .annotate(cnt=Count("id"))
    ):
        _det_person_counts[str(row["person_id"])] = row["cnt"]

    _det_org_counts = {}
    for row in (
        Detection.objects.filter(case=case, organization__isnull=False)
        .values("organization_id")
        .annotate(cnt=Count("id"))
    ):
        _det_org_counts[str(row["organization_id"])] = row["cnt"]

    _det_prop_counts = {}
    for row in (
        Detection.objects.filter(case=case, property_record__isnull=False)
        .values("property_record_id")
        .annotate(cnt=Count("id"))
    ):
        _det_prop_counts[str(row["property_record_id"])] = row["cnt"]

    _det_fi_counts = {}
    for row in (
        Detection.objects.filter(case=case, financial_instrument__isnull=False)
        .values("financial_instrument_id")
        .annotate(cnt=Count("id"))
    ):
        _det_fi_counts[str(row["financial_instrument_id"])] = row["cnt"]

    # ── 1. Collect nodes ──────────────────────────────────────────────

    # Persons
    for p in Person.objects.filter(case=case):
        pid = str(p.pk)
        node_ids.add(pid)
        node_type_counts["person"] += 1
        doc_count = PersonDocument.objects.filter(person=p).count()
        nodes.append(
            {
                "id": pid,
                "type": "person",
                "label": p.full_name,
                "metadata": {
                    "role_tags": p.role_tags or [],
                    "aliases": p.aliases or [],
                    "date_of_death": p.date_of_death.isoformat() if p.date_of_death else None,
                    "signal_count": entity_signal_counts.get(pid, 0),
                    "detection_count": _det_person_counts.get(pid, 0),
                    "doc_count": doc_count,
                },
            }
        )

    # Organizations
    for o in Organization.objects.filter(case=case):
        oid = str(o.pk)
        node_ids.add(oid)
        node_type_counts["organization"] += 1
        doc_count = OrgDocument.objects.filter(org=o).count()
        nodes.append(
            {
                "id": oid,
                "type": "organization",
                "label": o.name,
                "metadata": {
                    "org_type": o.org_type,
                    "ein": o.ein,
                    "status": o.status,
                    "signal_count": entity_signal_counts.get(oid, 0),
                    "detection_count": _det_org_counts.get(oid, 0),
                    "doc_count": doc_count,
                },
            }
        )

    # Properties
    for prop in Property.objects.filter(case=case):
        propid = str(prop.pk)
        node_ids.add(propid)
        node_type_counts["property"] += 1
        nodes.append(
            {
                "id": propid,
                "type": "property",
                "label": prop.address or prop.parcel_number or propid[:8],
                "metadata": {
                    "parcel_number": prop.parcel_number,
                    "county": prop.county,
                    "assessed_value": str(prop.assessed_value) if prop.assessed_value else None,
                    "purchase_price": str(prop.purchase_price) if prop.purchase_price else None,
                    "signal_count": entity_signal_counts.get(propid, 0),
                    "detection_count": _det_prop_counts.get(propid, 0),
                    "doc_count": 0,
                },
            }
        )

    # Financial Instruments
    for fi in FinancialInstrument.objects.filter(case=case):
        fiid = str(fi.pk)
        node_ids.add(fiid)
        node_type_counts["financial_instrument"] += 1
        nodes.append(
            {
                "id": fiid,
                "type": "financial_instrument",
                "label": f"{fi.instrument_type} {fi.filing_number or ''}".strip() or fiid[:8],
                "metadata": {
                    "instrument_type": fi.instrument_type,
                    "filing_number": fi.filing_number,
                    "filing_date": fi.filing_date.isoformat() if fi.filing_date else None,
                    "amount": str(fi.amount) if fi.amount else None,
                    "signal_count": entity_signal_counts.get(fiid, 0),
                    "detection_count": _det_fi_counts.get(fiid, 0),
                    "doc_count": 0,
                },
            }
        )

    # ── 2. Derive edges ───────────────────────────────────────────────

    # PersonOrganization → OFFICER_OF / ROLE edges
    for po in PersonOrganization.objects.filter(person__case=case).select_related("person", "org"):
        src = str(po.person_id)
        tgt = str(po.org_id)
        if src in node_ids and tgt in node_ids:
            edges.append(
                {
                    "source": src,
                    "target": tgt,
                    "relationship": "OFFICER_OF",
                    "label": po.role or "Member",
                    "weight": 3,
                    "metadata": {
                        "start_date": po.start_date.isoformat() if po.start_date else None,
                        "end_date": po.end_date.isoformat() if po.end_date else None,
                    },
                }
            )

    # PersonDocument → CO_APPEARS_IN (person ↔ person via shared documents)
    # Build a lookup: document_id → list of person_ids
    _doc_persons = {}
    for pd in PersonDocument.objects.filter(person__case=case):
        doc_id = str(pd.document_id)
        person_id = str(pd.person_id)
        _doc_persons.setdefault(doc_id, []).append(person_id)

    # Also build doc → org lookup for cross-type edges
    _doc_orgs = {}
    for od in OrgDocument.objects.filter(org__case=case):
        doc_id = str(od.document_id)
        org_id = str(od.org_id)
        _doc_orgs.setdefault(doc_id, []).append(org_id)

    # Create CO_APPEARS_IN edges for entities sharing documents
    _seen_co_appear = set()
    for doc_id, person_ids in _doc_persons.items():
        # Person ↔ Person (same document)
        for i, pa in enumerate(person_ids):
            for pb in person_ids[i + 1 :]:
                pair = tuple(sorted([pa, pb]))
                if pair not in _seen_co_appear:
                    _seen_co_appear.add(pair)
                    edges.append(
                        {
                            "source": pa,
                            "target": pb,
                            "relationship": "CO_APPEARS_IN",
                            "label": "Co-appears in document",
                            "weight": 1,
                            "metadata": {"document_ids": [doc_id]},
                        }
                    )

        # Person ↔ Organization (same document)
        org_ids = _doc_orgs.get(doc_id, [])
        for pa in person_ids:
            for oa in org_ids:
                pair = tuple(sorted([pa, oa]))
                if pair not in _seen_co_appear:
                    _seen_co_appear.add(pair)
                    edges.append(
                        {
                            "source": pa,
                            "target": oa,
                            "relationship": "CO_APPEARS_IN",
                            "label": "Co-appears in document",
                            "weight": 1,
                            "metadata": {"document_ids": [doc_id]},
                        }
                    )

    # Org ↔ Org (same document)
    for doc_id, org_ids in _doc_orgs.items():
        for i, oa in enumerate(org_ids):
            for ob in org_ids[i + 1 :]:
                pair = tuple(sorted([oa, ob]))
                if pair not in _seen_co_appear:
                    _seen_co_appear.add(pair)
                    edges.append(
                        {
                            "source": oa,
                            "target": ob,
                            "relationship": "CO_APPEARS_IN",
                            "label": "Co-appears in document",
                            "weight": 1,
                            "metadata": {"document_ids": [doc_id]},
                        }
                    )

    # Consolidate CO_APPEARS_IN: merge edges that share (source, target)
    # to accumulate all document_ids into one edge and increase weight.
    _co_appear_map = {}
    _other_edges = []
    for edge in edges:
        if edge["relationship"] == "CO_APPEARS_IN":
            pair_key = (edge["source"], edge["target"])
            if pair_key in _co_appear_map:
                existing = _co_appear_map[pair_key]
                existing["metadata"]["document_ids"].extend(edge["metadata"]["document_ids"])
                existing["weight"] += 1
            else:
                _co_appear_map[pair_key] = edge
        else:
            _other_edges.append(edge)
    edges = _other_edges + list(_co_appear_map.values())

    # PropertyTransaction → TRANSFERRED_TO / TRANSFERRED_FROM edges
    for tx in PropertyTransaction.objects.filter(property__case=case):
        prop_id = str(tx.property_id)
        if prop_id not in node_ids:
            continue
        tx_meta = {
            "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            "price": str(tx.price) if tx.price else None,
            "instrument_number": tx.instrument_number,
        }
        # Buyer → Property (PURCHASED)
        if tx.buyer_id and str(tx.buyer_id) in node_ids:
            edges.append(
                {
                    "source": str(tx.buyer_id),
                    "target": prop_id,
                    "relationship": "PURCHASED",
                    "label": f"Bought{(' $' + str(tx.price)) if tx.price else ''}",
                    "weight": 2,
                    "metadata": tx_meta,
                }
            )
        # Property → Seller (SOLD_BY)
        if tx.seller_id and str(tx.seller_id) in node_ids:
            edges.append(
                {
                    "source": prop_id,
                    "target": str(tx.seller_id),
                    "relationship": "SOLD_BY",
                    "label": f"Sold by{(' $' + str(tx.price)) if tx.price else ''}",
                    "weight": 2,
                    "metadata": tx_meta,
                }
            )

    # Relationship → direct person-to-person typed edges
    for rel in Relationship.objects.filter(case=case).select_related("person_a", "person_b"):
        src = str(rel.person_a_id)
        tgt = str(rel.person_b_id)
        if src in node_ids and tgt in node_ids:
            edges.append(
                {
                    "source": src,
                    "target": tgt,
                    "relationship": rel.relationship_type,
                    "label": rel.relationship_type.replace("_", " ").title(),
                    "weight": max(1, int(rel.confidence * 3)),
                    "metadata": {
                        "source_type": rel.source,
                        "confidence": rel.confidence,
                        "notes": rel.notes or "",
                    },
                }
            )

    # SocialMediaConnection → SOCIAL_CONNECTION edges
    for sc in SocialMediaConnection.objects.filter(case=case).select_related("person"):
        src = str(sc.person_id)
        if sc.connected_person_id:
            tgt = str(sc.connected_person_id)
            if src in node_ids and tgt in node_ids:
                edges.append(
                    {
                        "source": src,
                        "target": tgt,
                        "relationship": "SOCIAL_CONNECTION",
                        "label": f"{sc.platform} {sc.connection_type}".strip(),
                        "weight": 1,
                        "metadata": {
                            "platform": sc.platform,
                            "connection_type": sc.connection_type,
                        },
                    }
                )

    # ── 3. Collect timeline events ────────────────────────────────────
    from .models import FinancialSnapshot

    timeline_events = []

    # Documents layer — uploaded_at
    for doc in Document.objects.filter(case=case).only(
        "pk", "display_name", "filename", "uploaded_at", "doc_type"
    ):
        if doc.uploaded_at:
            timeline_events.append(
                {
                    "id": str(doc.pk),
                    "layer": "document",
                    "date": doc.uploaded_at.isoformat(),
                    "label": doc.display_name or doc.filename,
                    "metadata": {"doc_type": doc.doc_type},
                }
            )

    # Signals layer — detected_at
    for sig in Signal.objects.filter(case=case).only(
        "pk", "rule_id", "severity", "detected_at", "detected_summary", "trigger_entity_id"
    ):
        if sig.detected_at:
            timeline_events.append(
                {
                    "id": str(sig.pk),
                    "layer": "signal",
                    "date": sig.detected_at.isoformat(),
                    "label": f"{sig.rule_id}: {(sig.detected_summary or '')[:60]}",
                    "metadata": {
                        "severity": sig.severity,
                        "rule_id": sig.rule_id,
                        "entity_id": str(sig.trigger_entity_id) if sig.trigger_entity_id else None,
                    },
                }
            )

    # Financial layer — tax_year (converted to Jan 1 of that year)
    for snap in FinancialSnapshot.objects.filter(case=case).only(
        "pk", "tax_year", "total_revenue", "total_expenses", "ein", "organization_id"
    ):
        timeline_events.append(
            {
                "id": str(snap.pk),
                "layer": "financial",
                "date": f"{snap.tax_year}-01-01T00:00:00+00:00",
                "label": f"FY{snap.tax_year} 990 Filing",
                "metadata": {
                    "tax_year": snap.tax_year,
                    "total_revenue": str(snap.total_revenue) if snap.total_revenue else None,
                    "total_expenses": str(snap.total_expenses) if snap.total_expenses else None,
                    "entity_id": str(snap.organization_id) if snap.organization_id else None,
                },
            }
        )

    # Property transactions layer — transaction_date
    for tx in PropertyTransaction.objects.filter(property__case=case).select_related("property"):
        if tx.transaction_date:
            prop_label = tx.property.address or tx.property.parcel_number or "Property"
            timeline_events.append(
                {
                    "id": str(tx.pk),
                    "layer": "transaction",
                    "date": f"{tx.transaction_date.isoformat()}T00:00:00+00:00",
                    "label": (f"{prop_label}: {tx.buyer_name or '?'} ← {tx.seller_name or '?'}"),
                    "metadata": {
                        "price": str(tx.price) if tx.price else None,
                        "property_id": str(tx.property_id),
                        "buyer_id": str(tx.buyer_id) if tx.buyer_id else None,
                        "seller_id": str(tx.seller_id) if tx.seller_id else None,
                    },
                }
            )

    # Sort events by date
    timeline_events.sort(key=lambda e: e["date"])

    # ── 4. Build response ─────────────────────────────────────────────

    return JsonResponse(
        {
            "nodes": nodes,
            "edges": edges,
            "timeline_events": timeline_events,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_events": len(timeline_events),
                "node_types": node_type_counts,
            },
        }
    )


# ---------------------------------------------------------------------------
# Cross-case entity list
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_entity_collection(request):
    """Cross-case entity browser. Unions persons, organizations, properties, financial instruments.

    TODO(SEC-010): When user-level auth is added, scope all sub-queries to
    cases the authenticated user has access to.
    """
    raw_type = request.GET.get("type")
    raw_query = request.GET.get("q", "").strip()
    raw_case_id = request.GET.get("case_id")
    limit = min(int(request.GET.get("limit", "100")), 200)
    offset = int(request.GET.get("offset", "0"))

    results = []

    entity_types = (
        [raw_type]
        if raw_type in ("person", "organization", "property", "financial_instrument")
        else ["person", "organization", "property", "financial_instrument"]
    )

    for etype in entity_types:
        if etype == "person":
            qs = Person.objects.select_related("case").order_by("-created_at")
            if raw_query:
                qs = qs.filter(full_name__icontains=raw_query)
            if raw_case_id:
                qs = qs.filter(case_id=raw_case_id)
            for p in qs[:limit]:
                data = serialize_person(p)
                data["case_name"] = p.case.name
                results.append(data)

        elif etype == "organization":
            qs = Organization.objects.select_related("case").order_by("-created_at")
            if raw_query:
                qs = qs.filter(name__icontains=raw_query)
            if raw_case_id:
                qs = qs.filter(case_id=raw_case_id)
            for o in qs[:limit]:
                data = serialize_organization(o)
                data["case_name"] = o.case.name
                results.append(data)

        elif etype == "property":
            qs = Property.objects.select_related("case").order_by("-created_at")
            if raw_query:
                qs = qs.filter(address__icontains=raw_query)
            if raw_case_id:
                qs = qs.filter(case_id=raw_case_id)
            for p in qs[:limit]:
                data = serialize_property(p)
                data["case_name"] = p.case.name
                results.append(data)

        elif etype == "financial_instrument":
            qs = FinancialInstrument.objects.select_related("case").order_by("-created_at")
            if raw_query:
                qs = qs.filter(filing_number__icontains=raw_query)
            if raw_case_id:
                qs = qs.filter(case_id=raw_case_id)
            for fi in qs[:limit]:
                data = serialize_financial_instrument(fi)
                data["case_name"] = fi.case.name
                results.append(data)

    # Sort by created_at descending, truncate
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    total = len(results)
    paged = results[offset : offset + limit]

    return JsonResponse(
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": paged,
        }
    )


# ---------------------------------------------------------------------------
# Activity feed (recent audit log entries)
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_activity_feed(request):
    """Recent audit log entries, optionally scoped to a case.

    TODO(SEC-010): When user-level auth is added, scope this queryset to
    cases the authenticated user has access to.
    """
    limit = min(int(request.GET.get("limit", "20")), 100)
    qs = AuditLog.objects.order_by("-performed_at")

    raw_case_id = request.GET.get("case_id")
    if raw_case_id is not None:
        qs = qs.filter(case_id=raw_case_id)

    results = [serialize_audit_log(entry) for entry in qs[:limit]]
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
            try:
                _process_uploaded_file(
                    uploaded_file=request.FILES["file"],
                    case=form.cleaned_data["case"],
                    doc_type_hint=form.cleaned_data["doc_type"],
                    source_url=form.cleaned_data.get("source_url"),
                )
            except UploadValidationError as exc:
                form.add_error("file", str(exc))
                return render(
                    request,
                    "investigations/document_upload.html",
                    {"form": form, "title": "Upload Document"},
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
        except UploadValidationError as exc:
            # Expected validation failure — safe to return the message
            logger.warning(
                "bulk_upload_file_rejected",
                extra={
                    "case_id": str(case.pk),
                    "doc_filename": uploaded_file.name,
                    "reason": str(exc),
                },
            )
            errors.append({"filename": uploaded_file.name, "error": str(exc)})
        except Exception:
            # Unexpected error — log full details but return generic message
            # to avoid leaking internal details (SEC-013)
            logger.exception(
                "bulk_upload_file_failed",
                extra={
                    "case_id": str(case.pk),
                    "doc_filename": uploaded_file.name,
                },
            )
            errors.append(
                {
                    "filename": uploaded_file.name,
                    "error": "Internal error processing file.",
                }
            )

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

    referral = serializer.save()
    AuditLog.log(
        action=AuditAction.REFERRAL_CREATED,
        table_name="government_referrals",
        record_id=None,  # AutoField PK, not UUID
        case_id=case.pk,
        after_state={"agency_name": referral.agency_name, "status": referral.status},
        performed_by=getattr(request, "api_token", None),
        notes=f"referral_id={referral.referral_id}",
    )
    return JsonResponse(serializer.data, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_case_referral_detail(request, pk, referral_id):
    """Retrieve, update, or delete a single government referral.

    Restored from truncation — see SEC-006 in SECURITY_AUDIT.md.
    """
    case = get_object_or_404(Case, pk=pk)
    referral = get_object_or_404(GovernmentReferral, referral_id=referral_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        before = {"status": referral.status, "notes": referral.notes}
        serializer = ReferralUpdateSerializer(data=payload, instance=referral)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()

        # Use specific audit action if status changed
        new_status = serializer.validated_data.get("status", referral.status)
        if new_status == "SUBMITTED" and before["status"] != "SUBMITTED":
            audit_action = AuditAction.REFERRAL_SUBMITTED
        elif new_status != before["status"]:
            audit_action = AuditAction.REFERRAL_STATUS_CHANGED
        else:
            audit_action = AuditAction.RECORD_UPDATED

        AuditLog.log(
            action=audit_action,
            table_name="government_referrals",
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
            notes=f"referral_id={referral.referral_id}",
        )
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        ref_id = referral.referral_id
        agency = referral.agency_name
        referral.delete()
        AuditLog.log(
            action=AuditAction.RECORD_DELETED,
            table_name="government_referrals",
            case_id=case.pk,
            before_state={"agency_name": agency},
            performed_by=getattr(request, "api_token", None),
            notes=f"referral_id={ref_id}",
        )
        return HttpResponse(status=204)

    return JsonResponse(serialize_referral(referral))


# ---------------------------------------------------------------------------
# Detection collection + detail  (Milestone 2)
# ---------------------------------------------------------------------------

DETECTION_SORT_FIELDS = {
    "detected_at",
    "severity",
    "status",
    "signal_type",
    "confidence_score",
    "id",
}


@require_http_methods(["GET", "POST"])
def api_case_detection_collection(request, pk):
    """List detections for a case (GET) or create one manually (POST)."""
    case = get_object_or_404(Case, pk=pk)

    if request.method == "POST":
        payload, err = _parse_json_body(request)
        if err is not None:
            return err

        serializer = DetectionIntakeSerializer(data=payload, case=case)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        detection = serializer.save()
        AuditLog.log(
            action=AuditAction.RECORD_CREATED,
            table_name="detections",
            record_id=detection.pk,
            case_id=case.pk,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data, status=201)

    # GET — paginated, filterable list
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

    # Optional filters
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
    """Retrieve, update, or delete a single detection."""
    case = get_object_or_404(Case, pk=pk)
    detection = get_object_or_404(Detection, pk=detection_id, case=case)

    if request.method == "PATCH":
        payload, error_response = _parse_json_body(request)
        if error_response is not None:
            return error_response

        before = {
            "status": detection.status,
            "investigator_note": detection.investigator_note,
            "confidence_score": detection.confidence_score,
        }
        serializer = DetectionUpdateSerializer(data=payload, instance=detection)
        if not serializer.is_valid():
            return JsonResponse({"errors": serializer.errors}, status=400)

        serializer.save()

        # Determine the right audit action based on the new status
        new_status = serializer.validated_data.get("status", detection.status)
        if new_status == "CONFIRMED":
            audit_action = AuditAction.SIGNAL_CONFIRMED
        elif new_status == "DISMISSED":
            audit_action = AuditAction.SIGNAL_DISMISSED
        elif new_status == "ESCALATED":
            audit_action = AuditAction.SIGNAL_ESCALATED
        else:
            audit_action = AuditAction.RECORD_UPDATED

        AuditLog.log(
            action=audit_action,
            table_name="detections",
            record_id=detection.pk,
            case_id=case.pk,
            before_state=before,
            after_state=serializer.validated_data,
            performed_by=getattr(request, "api_token", None),
        )
        return JsonResponse(serializer.data)

    if request.method == "DELETE":
        detection_pk = detection.pk
        signal_type = detection.signal_type
        detection.delete()
        AuditLog.log(
            action=AuditAction.RECORD_DELETED,
            table_name="detections",
            record_id=detection_pk,
            case_id=case.pk,
            before_state={"signal_type": signal_type},
            performed_by=getattr(request, "api_token", None),
        )
        return HttpResponse(status=204)

    return JsonResponse(serialize_detection(detection))


# ---------------------------------------------------------------------------
# Re-evaluate signals  (Milestone 2)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def api_case_reevaluate_signals(request, pk):
    """Re-run signal detection rules across all case documents.

    Returns any newly persisted detections (deduplication prevents
    re-persisting existing ones).
    """
    case = get_object_or_404(Case, pk=pk)

    from .signal_rules import evaluate_case, evaluate_document, persist_signals

    all_triggers = []
    documents = list(
        case.documents.filter(
            extracted_text__isnull=False,
        ).exclude(extracted_text="")
    )

    for doc in documents:
        all_triggers.extend(evaluate_document(case, doc))
    # Case-scoped rules (cross-document patterns)
    if documents:
        all_triggers.extend(evaluate_case(case, trigger_doc=documents[-1]))

    new_detections = persist_signals(case, all_triggers)

    AuditLog.log(
        action=AuditAction.RECORD_UPDATED,
        table_name="detections",
        case_id=case.pk,
        after_state={
            "documents_evaluated": len(documents),
            "triggers_found": len(all_triggers),
            "new_detections": len(new_detections),
        },
        performed_by=getattr(request, "api_token", None),
        notes="reevaluate_signals",
    )

    return JsonResponse(
        {
            "documents_evaluated": len(documents),
            "triggers_found": len(all_triggers),
            "new_detections": [serialize_detection(d) for d in new_detections],
        }
    )


# ---------------------------------------------------------------------------
# Case intelligence dashboard & coverage audit
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def api_case_dashboard(request, pk):
    """Return a comprehensive case intelligence summary for the dashboard.

    Aggregates everything an investigator needs at a glance:
    - Case metadata and status
    - Document processing statistics (total, by type, by extraction status)
    - Entity counts (persons, orgs, properties, instruments)
    - Signal breakdown (by severity, by status, by rule)
    - Detection and finding summaries
    - Financial snapshot overview (if 990 data exists)
    - Pipeline health (extraction success rate, AI vs regex counts)

    Response shape:
      {
        "case": { ... },
        "documents": { "total": N, "by_type": {...}, "by_status": {...} },
        "entities": { "persons": N, "orgs": N, "properties": N, "instruments": N },
        "signals": { "total": N, "by_severity": {...}, "by_status": {...}, "top_rules": [...] },
        "detections": { "total": N, "confirmed": N, "pending": N },
        "findings": { "total": N, "by_severity": {...}, "by_status": {...} },
        "financials": { "years_covered": N, "total_revenue": "...", "total_expenses": "..." },
        "pipeline": { "extraction_success_rate": 0.95, "ai_enhanced_count": N }
      }
    """

    from django.db.models import Count, Sum

    case = get_object_or_404(Case, pk=pk)

    # ── Documents ──────────────────────────────────────────────
    docs = case.documents.all()
    doc_type_counts = dict(
        docs.values_list("doc_type").annotate(n=Count("id")).values_list("doc_type", "n")
    )
    ext_status_counts = dict(
        docs.values_list("extraction_status")
        .annotate(n=Count("id"))
        .values_list("extraction_status", "n")
    )
    total_docs = docs.count()
    completed_extractions = ext_status_counts.get("COMPLETED", 0)
    extraction_rate = round(completed_extractions / total_docs, 2) if total_docs > 0 else 0.0

    # Count AI-enhanced documents (have ingestion_metadata with ai_proposals > 0)
    ai_enhanced = docs.filter(ingestion_metadata__meta__ai_proposals__gt=0).count()

    # Renamed files (have a display_name set)
    renamed_count = docs.exclude(display_name="").exclude(display_name__isnull=True).count()

    # ── Entities ───────────────────────────────────────────────
    person_count = case.persons.count()
    org_count = case.organizations.count()
    property_count = case.properties.count()
    instrument_count = case.financial_instruments.count()

    # ── Signals ────────────────────────────────────────────────
    signals = Signal.objects.filter(case=case)
    signal_total = signals.count()
    sev_counts = dict(
        signals.values_list("severity").annotate(n=Count("id")).values_list("severity", "n")
    )
    status_counts = dict(
        signals.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )

    # Top triggered rules
    rule_counts = (
        signals.values("rule_id", "detected_summary").annotate(n=Count("id")).order_by("-n")[:10]
    )
    top_rules = [
        {"rule_id": r["rule_id"], "summary": r["detected_summary"], "count": r["n"]}
        for r in rule_counts
    ]

    # ── Detections ─────────────────────────────────────────────
    from .models import Detection

    detections = Detection.objects.filter(case=case)
    detection_total = detections.count()
    detection_confirmed = detections.filter(status="CONFIRMED").count()
    detection_pending = detections.filter(status="OPEN").count()

    # ── Findings ───────────────────────────────────────────────
    findings = case.findings.all()
    finding_total = findings.count()
    finding_sev = dict(
        findings.values_list("severity").annotate(n=Count("id")).values_list("severity", "n")
    )
    finding_status = dict(
        findings.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )

    # ── Financials ─────────────────────────────────────────────
    from .models import FinancialSnapshot

    snapshots = FinancialSnapshot.objects.filter(case=case).order_by("tax_year")
    years_covered = snapshots.values("tax_year").distinct().count()
    fin_agg = snapshots.aggregate(
        total_rev=Sum("total_revenue"),
        total_exp=Sum("total_expenses"),
    )
    total_revenue = str(fin_agg["total_rev"] or 0)
    total_expenses = str(fin_agg["total_exp"] or 0)

    # Year-over-year data for charts
    yearly = list(
        snapshots.values("tax_year")
        .annotate(
            revenue=Sum("total_revenue"),
            expenses=Sum("total_expenses"),
        )
        .order_by("tax_year")
    )
    financial_timeline = [
        {
            "year": y["tax_year"],
            "revenue": str(y["revenue"] or 0),
            "expenses": str(y["expenses"] or 0),
        }
        for y in yearly
    ]

    return JsonResponse(
        {
            "case": {
                "id": str(case.pk),
                "name": case.name,
                "status": case.status,
                "created_at": case.created_at.isoformat(),
                "referral_ref": case.referral_ref or "",
            },
            "documents": {
                "total": total_docs,
                "by_type": doc_type_counts,
                "by_extraction_status": ext_status_counts,
                "renamed_count": renamed_count,
            },
            "entities": {
                "persons": person_count,
                "organizations": org_count,
                "properties": property_count,
                "financial_instruments": instrument_count,
                "total": person_count + org_count + property_count + instrument_count,
            },
            "signals": {
                "total": signal_total,
                "by_severity": sev_counts,
                "by_status": status_counts,
                "top_rules": top_rules,
            },
            "detections": {
                "total": detection_total,
                "confirmed": detection_confirmed,
                "pending": detection_pending,
            },
            "findings": {
                "total": finding_total,
                "by_severity": finding_sev,
                "by_status": finding_status,
            },
            "financials": {
                "years_covered": years_covered,
                "total_revenue": total_revenue,
                "total_expenses": total_expenses,
                "timeline": financial_timeline,
            },
            "pipeline": {
                "extraction_success_rate": extraction_rate,
                "ai_enhanced_count": ai_enhanced,
                "total_documents_processed": total_docs,
            },
        }
    )


@require_http_methods(["GET"])
def api_case_coverage(request, pk):
    """Return signal coverage gaps for a case.

    Calls the coverage_audit() function from the signal engine and returns
    actionable recommendations for improving signal detection coverage.

    Response shape:
      {
        "gaps": [
          {
            "rule_id": "SR-001",
            "rule_title": "Deceased signer",
            "gap_type": "RULE_BLIND",
            "message": "...",
            "recommendation": "..."
          },
          ...
        ],
        "coverage_score": 0.72,
        "total_rules": 29,
        "active_rules": 21,
        "blind_rules": 8
      }
    """
    case = get_object_or_404(Case, pk=pk)

    from .signal_rules import RULE_REGISTRY, coverage_audit

    gaps = coverage_audit(case)

    # Calculate coverage score
    total_rules = len(RULE_REGISTRY)
    blind_rule_ids = {g.rule_id for g in gaps if g.gap_type == "RULE_BLIND"}
    # META and ALL are not real rule IDs — don't count them
    blind_rule_ids.discard("META")
    blind_rule_ids.discard("ALL")
    active_rules = total_rules - len(blind_rule_ids)
    coverage_score = round(active_rules / total_rules, 2) if total_rules > 0 else 0.0

    return JsonResponse(
        {
            "gaps": [
                {
                    "rule_id": g.rule_id,
                    "rule_title": g.rule_title,
                    "gap_type": g.gap_type,
                    "message": g.message,
                    "recommendation": g.recommendation,
                }
                for g in gaps
            ],
            "coverage_score": coverage_score,
            "total_rules": total_rules,
            "active_rules": active_rules,
            "blind_rules": len(blind_rule_ids),
        }
    )


# ---------------------------------------------------------------------------
# Referral memo generation stub  (full AI in Milestone 3)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def api_case_referral_memo(request, pk):
    """Generate a referral memo document for a case.

    Milestone 2 stub: creates a placeholder memo document so the upload/view
    pipeline works end-to-end. Milestone 3 will replace the body text with
    AI-generated content (Claude/OpenAI API).
    """
    case = get_object_or_404(Case, pk=pk)

    # Gather case context for the stub memo
    doc_count = case.documents.count()
    signal_count = Signal.objects.filter(case=case).count()
    detection_count = Detection.objects.filter(case=case).count()
    finding_count = Finding.objects.filter(case=case).count()
    referral_count = GovernmentReferral.objects.filter(case=case).count()

    memo_text = (
        f"REFERRAL MEMO — {case.name}\n"
        f"{'=' * 60}\n\n"
        f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"Case Status: {case.status}\n"
        f"Reference: {case.referral_ref or 'N/A'}\n\n"
        f"CASE SUMMARY\n"
        f"{'-' * 40}\n"
        f"Documents: {doc_count}\n"
        f"Signals: {signal_count}\n"
        f"Detections: {detection_count}\n"
        f"Findings: {finding_count}\n"
        f"Referrals: {referral_count}\n\n"
        f"NOTES\n"
        f"{'-' * 40}\n"
        f"{case.notes or 'No case notes recorded.'}\n\n"
        f"[This is a placeholder memo. AI-generated narrative will be added in Milestone 3.]\n"
    )

    # Create the memo as a generated document
    document = Document.objects.create(
        case=case,
        filename=f"referral-memo-{timezone.now().strftime('%Y%m%d-%H%M%S')}.txt",
        file_path="",
        sha256_hash=hashlib.sha256(memo_text.encode()).hexdigest(),
        file_size=len(memo_text.encode()),
        doc_type=DocumentType.REFERRAL_MEMO,
        is_generated=True,
        extracted_text=memo_text,
        ocr_status=OcrStatus.NOT_NEEDED,
        uploaded_at=timezone.now(),
        updated_at=timezone.now(),
    )

    AuditLog.log(
        action=AuditAction.RECORD_CREATED,
        table_name="documents",
        record_id=document.pk,
        case_id=case.pk,
        after_state={
            "filename": document.filename,
            "doc_type": "REFERRAL_MEMO",
            "is_generated": True,
        },
        performed_by=getattr(request, "api_token", None),
        notes="referral_memo_stub",
    )

    return JsonResponse(serialize_document(document), status=201)


# ---------------------------------------------------------------------------
# AI endpoints (Phase 5)
# ---------------------------------------------------------------------------


@require_http_methods(["POST"])
def api_ai_summarize(request, pk):
    """Summarize a signal, entity, or other evidence target for a case.

    POST body (JSON):
        target_type: "signal" | "entity" | "detection" | "finding"
        target_id:   UUID string of the target object
    """
    case = get_object_or_404(Case, pk=pk)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    target_type = body.get("target_type", "")
    target_id = body.get("target_id", "")
    if not target_type or not target_id:
        return JsonResponse({"error": "Both target_type and target_id are required"}, status=400)

    from .ai_proxy import ai_summarize

    result = ai_summarize(case, target_type, target_id)
    if "error" in result:
        status = 429 if "Rate limit" in result["error"] else 500
        return JsonResponse(result, status=status)
    return JsonResponse(result)


@require_http_methods(["POST"])
def api_ai_connections(request, pk):
    """Suggest hidden connections between entities in a case.

    POST body (JSON):
        entity_id: (optional) UUID string to focus analysis on a specific entity
    """
    case = get_object_or_404(Case, pk=pk)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    entity_id = body.get("entity_id")

    from .ai_proxy import ai_connections

    result = ai_connections(case, entity_id=entity_id)
    if "error" in result:
        status = 429 if "Rate limit" in result["error"] else 500
        return JsonResponse(result, status=status)
    return JsonResponse(result)


@require_http_methods(["POST"])
def api_ai_narrative(request, pk):
    """Draft an investigative narrative from detection evidence.

    POST body (JSON):
        detection_ids: list of UUID strings for the detections to base the narrative on
        tone:          (optional) "formal" | "executive" | "technical" — defaults to "formal"
    """
    case = get_object_or_404(Case, pk=pk)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    detection_ids = body.get("detection_ids", [])
    if not detection_ids or not isinstance(detection_ids, list):
        return JsonResponse({"error": "detection_ids must be a non-empty list"}, status=400)

    tone = body.get("tone", "formal")
    if tone not in ("formal", "executive", "technical"):
        return JsonResponse(
            {"error": "tone must be one of: formal, executive, technical"}, status=400
        )

    from .ai_proxy import ai_narrative

    result = ai_narrative(case, detection_ids, tone)
    if "error" in result:
        status = 429 if "Rate limit" in result["error"] else 500
        return JsonResponse(result, status=status)
    return JsonResponse(result)


@require_http_methods(["POST"])
def api_ai_ask(request, pk):
    """Free-form AI question about a case, with multi-turn conversation support.

    POST body (JSON):
        question:             the user's question string
        conversation_history: (optional) list of {"role": "user"|"assistant", "content": "..."}
    """
    case = get_object_or_404(Case, pk=pk)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    question = body.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "question is required"}, status=400)

    conversation_history = body.get("conversation_history", [])

    from .ai_proxy import ai_ask

    result = ai_ask(case, question, conversation_history)
    if "error" in result:
        status = 429 if "Rate limit" in result["error"] else 500
        return JsonResponse(result, status=status)
    return JsonResponse(result)
