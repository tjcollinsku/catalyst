import re

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Case,
    Document,
    EvidenceWeight,
    Finding,
    FindingSource,
    FindingStatus,
    Severity,
)


def _serialize_datetime(value):
    if value is None:
        return None
    return value.isoformat()


def serialize_document(document: Document) -> dict:
    return {
        "id": str(document.pk),
        "filename": document.filename,
        "display_name": getattr(document, "display_name", "") or "",
        "file_path": document.file_path,
        "sha256_hash": document.sha256_hash,
        "file_size": document.file_size,
        "doc_type": document.doc_type,
        "is_generated": document.is_generated,
        "doc_subtype": document.doc_subtype,
        "source_url": document.source_url,
        "ocr_status": document.ocr_status,
        "extraction_status": getattr(document, "extraction_status", "PENDING"),
        "extraction_notes": getattr(document, "extraction_notes", ""),
        "uploaded_at": _serialize_datetime(document.uploaded_at),
        "updated_at": _serialize_datetime(document.updated_at),
    }


def serialize_case(case: Case) -> dict:
    return {
        "id": str(case.pk),
        "name": case.name,
        "status": case.status,
        "notes": case.notes,
        "referral_ref": case.referral_ref,
        "created_at": _serialize_datetime(case.created_at),
        "updated_at": _serialize_datetime(case.updated_at),
    }


def serialize_case_detail(case: Case) -> dict:
    payload = serialize_case(case)
    payload["documents"] = [
        serialize_document(document) for document in case.documents.order_by("-uploaded_at")
    ]
    return payload


class CaseIntakeSerializer:
    allowed_fields = {"name", "status", "notes", "referral_ref"}

    def __init__(self, data=None, instance=None):
        self.initial_data = data or {}
        self.instance = instance
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_case(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        self.validated_data = {
            "name": self.initial_data.get("name"),
            "status": self.initial_data.get("status", Case._meta.get_field("status").default),
            "notes": self.initial_data.get("notes") or "",
            "referral_ref": self.initial_data.get("referral_ref") or "",
        }

        candidate = Case(**self.validated_data)
        try:
            candidate.full_clean(validate_unique=False)
        except ValidationError as exc:
            self._errors = exc.message_dict
            return False

        self.validated_data = {
            "name": candidate.name,
            "status": candidate.status,
            "notes": candidate.notes,
            "referral_ref": candidate.referral_ref,
        }
        return True

    def save(self) -> Case:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance = Case.objects.create(**self.validated_data)
        return self.instance


class CaseUpdateSerializer:
    allowed_fields = {"status", "notes", "referral_ref"}

    def __init__(self, data=None, instance=None):
        self.initial_data = data or {}
        self.instance = instance
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_case(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": ["A case instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": ["Provide at least one updatable field in the payload."]
            }
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        self.validated_data = {
            "status": self.initial_data.get("status", self.instance.status),
            "notes": self.initial_data.get("notes", self.instance.notes),
            "referral_ref": self.initial_data.get("referral_ref", self.instance.referral_ref),
        }

        if self.validated_data["notes"] is None:
            self.validated_data["notes"] = ""

        if self.validated_data["referral_ref"] is None:
            self.validated_data["referral_ref"] = ""

        self.instance.status = self.validated_data["status"]
        self.instance.notes = self.validated_data["notes"]
        self.instance.referral_ref = self.validated_data["referral_ref"]

        try:
            self.instance.full_clean(validate_unique=False)
        except ValidationError as exc:
            self._errors = exc.message_dict
            return False

        return True

    def save(self) -> Case:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance.updated_at = timezone.now()
        self.instance.save(update_fields=["status", "notes", "referral_ref", "updated_at"])
        return self.instance


class DocumentIntakeSerializer:
    allowed_fields = {
        "filename",
        "file_path",
        "sha256_hash",
        "file_size",
        "doc_type",
        "is_generated",
        "doc_subtype",
        "source_url",
        "ocr_status",
        "extracted_text",
    }

    def __init__(self, data=None, instance=None, case=None):
        self.initial_data = data or {}
        self.instance = instance
        self.case = case
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_document(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.case is None:
            self._errors = {"non_field_errors": ["A case instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        self.validated_data = {
            "filename": self.initial_data.get("filename"),
            "file_path": self.initial_data.get("file_path"),
            "sha256_hash": self.initial_data.get("sha256_hash"),
            "file_size": self.initial_data.get("file_size"),
            "doc_type": self.initial_data.get(
                "doc_type", Document._meta.get_field("doc_type").default
            ),
            "is_generated": self.initial_data.get("is_generated", False),
            "doc_subtype": self.initial_data.get("doc_subtype", ""),
            "source_url": self.initial_data.get("source_url") or None,
            "ocr_status": self.initial_data.get(
                "ocr_status", Document._meta.get_field("ocr_status").default
            ),
            "extracted_text": self.initial_data.get("extracted_text") or None,
        }

        sha256_hash = self.validated_data["sha256_hash"]
        if not isinstance(sha256_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256_hash):
            self._errors = {"sha256_hash": ["Enter a valid 64-character hexadecimal SHA-256 hash."]}
            return False

        self.validated_data["sha256_hash"] = sha256_hash.lower()

        candidate = Document(case=self.case, **self.validated_data)
        try:
            candidate.full_clean(validate_unique=False)
        except ValidationError as exc:
            self._errors = exc.message_dict
            return False

        self.validated_data = {
            "filename": candidate.filename,
            "file_path": candidate.file_path,
            "sha256_hash": candidate.sha256_hash,
            "file_size": candidate.file_size,
            "doc_type": candidate.doc_type,
            "is_generated": candidate.is_generated,
            "doc_subtype": candidate.doc_subtype,
            "source_url": candidate.source_url,
            "ocr_status": candidate.ocr_status,
            "extracted_text": candidate.extracted_text,
        }
        return True

    def save(self) -> Document:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance = Document.objects.create(case=self.case, **self.validated_data)
        return self.instance


class DocumentUpdateSerializer:
    allowed_fields = {
        "doc_type",
        "is_generated",
        "doc_subtype",
        "source_url",
        "ocr_status",
        "extracted_text",
    }

    def __init__(self, data=None, instance=None):
        self.initial_data = data or {}
        self.instance = instance
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_document(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": ["A document instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": ["Provide at least one updatable field in the payload."]
            }
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        self.validated_data = {
            "doc_type": self.initial_data.get("doc_type", self.instance.doc_type),
            "is_generated": self.initial_data.get("is_generated", self.instance.is_generated),
            "doc_subtype": self.initial_data.get("doc_subtype", self.instance.doc_subtype),
            "source_url": self.initial_data.get("source_url", self.instance.source_url),
            "ocr_status": self.initial_data.get("ocr_status", self.instance.ocr_status),
            "extracted_text": self.initial_data.get("extracted_text", self.instance.extracted_text),
        }

        if self.validated_data["source_url"] == "":
            self.validated_data["source_url"] = None

        if self.validated_data["extracted_text"] == "":
            self.validated_data["extracted_text"] = None

        self.instance.doc_type = self.validated_data["doc_type"]
        self.instance.is_generated = self.validated_data["is_generated"]
        self.instance.doc_subtype = self.validated_data["doc_subtype"]
        self.instance.source_url = self.validated_data["source_url"]
        self.instance.ocr_status = self.validated_data["ocr_status"]
        self.instance.extracted_text = self.validated_data["extracted_text"]

        try:
            self.instance.full_clean(validate_unique=False)
        except ValidationError as exc:
            self._errors = exc.message_dict
            return False

        return True

    def save(self) -> Document:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance.updated_at = timezone.now()
        self.instance.save(
            update_fields=[
                "doc_type",
                "is_generated",
                "doc_subtype",
                "source_url",
                "ocr_status",
                "extracted_text",
                "updated_at",
            ]
        )
        return self.instance


# ---------------------------------------------------------------------------
# Entity serializers (cross-case)
# ---------------------------------------------------------------------------


def serialize_person(person) -> dict:
    return {
        "id": str(person.pk),
        "entity_type": "person",
        "name": person.full_name,
        "case_id": str(person.case_id),
        "role_tags": person.role_tags,
        "aliases": person.aliases,
        "date_of_death": person.date_of_death.isoformat() if person.date_of_death else None,
        "notes": person.notes,
        "created_at": _serialize_datetime(person.created_at),
        "updated_at": _serialize_datetime(person.updated_at),
    }


def serialize_organization(org) -> dict:
    return {
        "id": str(org.pk),
        "entity_type": "organization",
        "name": org.name,
        "case_id": str(org.case_id),
        "org_type": org.org_type,
        "ein": org.ein,
        "registration_state": org.registration_state,
        "status": org.status,
        "formation_date": org.formation_date.isoformat() if org.formation_date else None,
        "notes": org.notes or "",
        "created_at": _serialize_datetime(org.created_at),
        "updated_at": _serialize_datetime(org.updated_at),
    }


def serialize_property(prop) -> dict:
    return {
        "id": str(prop.pk),
        "entity_type": "property",
        "name": prop.address or prop.parcel_number or str(prop.pk)[:8],
        "case_id": str(prop.case_id),
        "parcel_number": prop.parcel_number,
        "address": prop.address,
        "county": prop.county,
        "assessed_value": str(prop.assessed_value) if prop.assessed_value else None,
        "purchase_price": str(prop.purchase_price) if prop.purchase_price else None,
        "notes": prop.notes or "",
        "created_at": _serialize_datetime(prop.created_at),
        "updated_at": _serialize_datetime(prop.updated_at),
    }


def serialize_financial_instrument(fi) -> dict:
    return {
        "id": str(fi.pk),
        "entity_type": "financial_instrument",
        "name": f"{fi.instrument_type} {fi.filing_number or ''}".strip() or str(fi.pk)[:8],
        "case_id": str(fi.case_id),
        "instrument_type": fi.instrument_type,
        "filing_number": fi.filing_number,
        "filing_date": fi.filing_date.isoformat() if fi.filing_date else None,
        "amount": str(fi.amount) if fi.amount else None,
        "anomaly_flags": fi.anomaly_flags,
        "notes": fi.notes or "",
        "created_at": _serialize_datetime(fi.created_at),
        "updated_at": _serialize_datetime(fi.updated_at),
    }


def serialize_audit_log(entry) -> dict:
    return {
        "id": str(entry.pk),
        "case_id": str(entry.case_id) if entry.case_id else None,
        "table_name": entry.table_name,
        "record_id": str(entry.record_id) if entry.record_id else None,
        "action": entry.action,
        "performed_by": entry.performed_by or "",
        "performed_at": _serialize_datetime(entry.performed_at),
        "notes": entry.notes or "",
    }


# ---------------------------------------------------------------------------
# InvestigatorNote serializers
# ---------------------------------------------------------------------------

_VALID_NOTE_TARGET_TYPES = {
    "case",
    "document",
    "signal",
    "detection",
    "person",
    "organization",
    "property",
    "financial_instrument",
}


def serialize_note(note) -> dict:

    return {
        "id": str(note.pk),
        "case_id": str(note.case_id),
        "target_type": note.target_type,
        "target_id": str(note.target_id),
        "content": note.content,
        "created_by": note.created_by,
        "created_at": _serialize_datetime(note.created_at),
        "updated_at": _serialize_datetime(note.updated_at),
    }


class NoteIntakeSerializer:
    """Validates POST payloads for creating an InvestigatorNote."""

    allowed_fields = {"target_type", "target_id", "content", "created_by"}

    def __init__(self, data=None, case=None):
        self.initial_data = data or {}
        self.case = case
        self.instance = None
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_note(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.case is None:
            self._errors = {"non_field_errors": ["A case instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        target_type = (self.initial_data.get("target_type") or "").strip()
        if target_type not in _VALID_NOTE_TARGET_TYPES:
            self._errors = {
                "target_type": [
                    f"Invalid target_type. Expected one of: "
                    f"{', '.join(sorted(_VALID_NOTE_TARGET_TYPES))}."
                ]
            }
            return False

        target_id = (self.initial_data.get("target_id") or "").strip()
        if not target_id:
            self._errors = {"target_id": ["target_id is required."]}
            return False

        import uuid

        try:
            target_id = str(uuid.UUID(target_id))
        except (ValueError, AttributeError):
            self._errors = {"target_id": ["target_id must be a valid UUID."]}
            return False

        content = (self.initial_data.get("content") or "").strip()
        if not content:
            self._errors = {"content": ["Note content cannot be empty."]}
            return False

        self.validated_data = {
            "target_type": target_type,
            "target_id": target_id,
            "content": content,
            "created_by": (self.initial_data.get("created_by") or "").strip(),
        }
        return True

    def save(self):
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        from .models import InvestigatorNote

        self.instance = InvestigatorNote.objects.create(case=self.case, **self.validated_data)
        return self.instance


class NoteUpdateSerializer:
    """Validates PATCH payloads for updating an InvestigatorNote."""

    allowed_fields = {"content", "created_by"}

    def __init__(self, data=None, instance=None):
        self.initial_data = data or {}
        self.instance = instance
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_note(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": ["A note instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": ["Provide at least one updatable field in the payload."]
            }
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        new_content = self.initial_data.get("content", self.instance.content)
        if isinstance(new_content, str):
            new_content = new_content.strip()
        if not new_content:
            self._errors = {"content": ["Note content cannot be empty."]}
            return False

        self.validated_data = {
            "content": new_content,
            "created_by": self.initial_data.get("created_by", self.instance.created_by),
        }
        return True

    def save(self):
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance.content = self.validated_data["content"]
        self.instance.created_by = self.validated_data["created_by"]
        self.instance.updated_at = timezone.now()
        self.instance.save(update_fields=["content", "created_by", "updated_at"])
        return self.instance


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def serialize_finding(finding) -> dict:
    """Serialize a Finding instance to a JSON-safe dict."""
    from .signal_rules import RULE_REGISTRY

    rule_info = RULE_REGISTRY.get(finding.rule_id)

    return {
        "id": str(finding.pk),
        "rule_id": finding.rule_id,
        "title": finding.title or (
            rule_info.title if rule_info else finding.rule_id
        ),
        "description": finding.description or (
            rule_info.description if rule_info else ""
        ),
        "narrative": finding.narrative,
        "severity": finding.severity,
        "status": finding.status,
        "evidence_weight": finding.evidence_weight,
        "source": finding.source,
        "investigator_note": finding.investigator_note,
        "legal_refs": finding.legal_refs,
        "evidence_snapshot": finding.evidence_snapshot,
        "trigger_doc_id": (
            str(finding.trigger_doc_id)
            if finding.trigger_doc_id else None
        ),
        "trigger_doc_filename": (
            finding.trigger_doc.filename
            if finding.trigger_doc_id and finding.trigger_doc
            else None
        ),
        "trigger_entity_id": (
            str(finding.trigger_entity_id)
            if finding.trigger_entity_id else None
        ),
        "created_at": finding.created_at.isoformat(),
        "updated_at": finding.updated_at.isoformat(),
        "entity_links": [
            {
                "entity_id": str(link.entity_id),
                "entity_type": link.entity_type,
                "context_note": link.context_note,
            }
            for link in finding.entity_links.all()
        ],
        "document_links": [
            {
                "document_id": str(link.document_id),
                "document_filename": (
                    link.document.filename
                    if link.document else ""
                ),
                "page_reference": link.page_reference,
                "context_note": link.context_note,
            }
            for link in finding.document_links.select_related(
                "document"
            )
        ],
    }


_VALID_FINDING_STATUSES = {c.value for c in FindingStatus}
_VALID_EVIDENCE_WEIGHTS = {c.value for c in EvidenceWeight}
_VALID_SEVERITIES = {c.value for c in Severity}


class FindingIntakeSerializer:
    """Validates POST payloads for creating a new Finding (manual)."""

    allowed_fields = {
        "title",
        "narrative",
        "severity",
        "evidence_weight",
        "legal_refs",
        "investigator_note",
    }

    def __init__(self, data=None, case=None):
        self.initial_data = data or {}
        self.case = case
        self.instance = None
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_finding(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.case is None:
            self._errors = {"non_field_errors": [
                "A case instance is required."
            ]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": [
                "Expected a JSON object."
            ]}
            return False

        unexpected_fields = (
            sorted(set(self.initial_data.keys()) - self.allowed_fields)
        )
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        title = (self.initial_data.get("title") or "").strip()
        if not title:
            self._errors = {"title": ["Title is required."]}
            return False

        severity = (self.initial_data.get("severity") or "").strip()
        if severity not in _VALID_SEVERITIES:
            valid_list = ", ".join(sorted(_VALID_SEVERITIES))
            self._errors = {
                "severity": [
                    f"Invalid severity. Expected one of: {valid_list}."
                ]
            }
            return False

        evidence_weight = (
            self.initial_data.get("evidence_weight", EvidenceWeight.SPECULATIVE)
        )
        if evidence_weight not in _VALID_EVIDENCE_WEIGHTS:
            valid_list = ", ".join(sorted(_VALID_EVIDENCE_WEIGHTS))
            self._errors = {
                "evidence_weight": [
                    f"Invalid evidence_weight. "
                    f"Expected one of: {valid_list}."
                ]
            }
            return False

        legal_refs = self.initial_data.get("legal_refs", [])
        if not isinstance(legal_refs, list):
            self._errors = {"legal_refs": [
                "legal_refs must be a list of strings."
            ]}
            return False

        self.validated_data = {
            "case": self.case,
            "title": title,
            "narrative": (
                self.initial_data.get("narrative", "")
            ),
            "severity": severity,
            "evidence_weight": evidence_weight,
            "source": FindingSource.MANUAL,
            "status": FindingStatus.NEW,
            "legal_refs": legal_refs,
            "investigator_note": (
                self.initial_data.get("investigator_note", "")
            ),
        }
        return True

    def save(self) -> Finding:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance = Finding.objects.create(**self.validated_data)
        return self.instance


class FindingUpdateSerializer:
    """Validates PATCH payloads for updating a Finding."""

    allowed_fields = {
        "title",
        "narrative",
        "severity",
        "status",
        "evidence_weight",
        "investigator_note",
        "legal_refs",
    }

    def __init__(self, data=None, instance=None):
        self.initial_data = data or {}
        self.instance = instance
        self.validated_data = {}
        self._errors = {}

    @property
    def errors(self) -> dict:
        return self._errors

    @property
    def data(self) -> dict:
        if self.instance is None:
            return {}
        return serialize_finding(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": [
                "A finding instance is required."
            ]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": [
                "Expected a JSON object."
            ]}
            return False

        if not self.initial_data:
            self._errors = {"non_field_errors": [
                "Provide at least one updatable field in the payload."
            ]}
            return False

        unexpected_fields = (
            sorted(set(self.initial_data.keys()) - self.allowed_fields)
        )
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        new_status = self.initial_data.get(
            "status", self.instance.status
        )
        if new_status not in _VALID_FINDING_STATUSES:
            valid_list = ", ".join(sorted(_VALID_FINDING_STATUSES))
            self._errors = {"status": [
                f"Invalid status. Expected one of: {valid_list}."
            ]}
            return False

        new_note = self.initial_data.get(
            "investigator_note", self.instance.investigator_note
        )

        if new_status == FindingStatus.DISMISSED and not (
            new_note or ""
        ).strip():
            self._errors = {
                "investigator_note": [
                    "A dismissal rationale is required when "
                    "setting status to DISMISSED."
                ]
            }
            return False

        self.validated_data = {
            "status": new_status,
            "investigator_note": new_note or "",
        }

        if "title" in self.initial_data:
            self.validated_data["title"] = (
                self.initial_data["title"]
            )

        if "narrative" in self.initial_data:
            self.validated_data["narrative"] = (
                self.initial_data["narrative"]
            )

        if "severity" in self.initial_data:
            sev = self.initial_data["severity"]
            if sev not in _VALID_SEVERITIES:
                valid_list = ", ".join(sorted(_VALID_SEVERITIES))
                self._errors = {"severity": [
                    f"Invalid severity. Expected one of: {valid_list}."
                ]}
                return False
            self.validated_data["severity"] = sev

        if "evidence_weight" in self.initial_data:
            ew = self.initial_data["evidence_weight"]
            if ew not in _VALID_EVIDENCE_WEIGHTS:
                valid_list = ", ".join(
                    sorted(_VALID_EVIDENCE_WEIGHTS)
                )
                self._errors = {"evidence_weight": [
                    f"Invalid evidence_weight. "
                    f"Expected one of: {valid_list}."
                ]}
                return False
            self.validated_data["evidence_weight"] = ew

        if "legal_refs" in self.initial_data:
            lr = self.initial_data["legal_refs"]
            if not isinstance(lr, list):
                self._errors = {"legal_refs": [
                    "legal_refs must be a list of strings."
                ]}
                return False
            self.validated_data["legal_refs"] = lr

        return True

    def save(self) -> Finding:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance.status = self.validated_data["status"]
        self.instance.investigator_note = (
            self.validated_data["investigator_note"]
        )
        if "title" in self.validated_data:
            self.instance.title = self.validated_data["title"]
        if "narrative" in self.validated_data:
            self.instance.narrative = (
                self.validated_data["narrative"]
            )
        if "severity" in self.validated_data:
            self.instance.severity = self.validated_data["severity"]
        if "evidence_weight" in self.validated_data:
            self.instance.evidence_weight = (
                self.validated_data["evidence_weight"]
            )
        if "legal_refs" in self.validated_data:
            self.instance.legal_refs = self.validated_data["legal_refs"]

        update_fields = [
            "status",
            "investigator_note",
            "updated_at",
        ]
        if "title" in self.validated_data:
            update_fields.append("title")
        if "narrative" in self.validated_data:
            update_fields.append("narrative")
        if "severity" in self.validated_data:
            update_fields.append("severity")
        if "evidence_weight" in self.validated_data:
            update_fields.append("evidence_weight")
        if "legal_refs" in self.validated_data:
            update_fields.append("legal_refs")

        self.instance.updated_at = timezone.now()
        self.instance.save(update_fields=update_fields)
        return self.instance
