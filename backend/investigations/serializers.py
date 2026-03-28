from django.core.exceptions import ValidationError
from django.utils import timezone
import re

from .models import Case, Document, Signal, SignalStatus


def _serialize_datetime(value):
    if value is None:
        return None
    return value.isoformat()


def serialize_document(document: Document) -> dict:
    return {
        "id": str(document.pk),
        "filename": document.filename,
        "file_path": document.file_path,
        "sha256_hash": document.sha256_hash,
        "file_size": document.file_size,
        "doc_type": document.doc_type,
        "is_generated": document.is_generated,
        "doc_subtype": document.doc_subtype,
        "source_url": document.source_url,
        "ocr_status": document.ocr_status,
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
        serialize_document(document)
        for document in case.documents.order_by("-uploaded_at")
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

        unexpected_fields = sorted(
            set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        self.validated_data = {
            "name": self.initial_data.get("name"),
            "status": self.initial_data.get(
                "status", Case._meta.get_field("status").default
            ),
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
            self._errors = {"non_field_errors": [
                "A case instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": [
                    "Provide at least one updatable field in the payload."
                ]
            }
            return False

        unexpected_fields = sorted(
            set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        self.validated_data = {
            "status": self.initial_data.get("status", self.instance.status),
            "notes": self.initial_data.get("notes", self.instance.notes),
            "referral_ref": self.initial_data.get(
                "referral_ref", self.instance.referral_ref
            ),
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
        self.instance.save(
            update_fields=["status", "notes", "referral_ref", "updated_at"])
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
            self._errors = {"non_field_errors": [
                "A case instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        unexpected_fields = sorted(
            set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
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
            self._errors = {
                "sha256_hash": [
                    "Enter a valid 64-character hexadecimal SHA-256 hash."
                ]
            }
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
        self.instance = Document.objects.create(
            case=self.case, **self.validated_data)
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
            self._errors = {"non_field_errors": [
                "A document instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": [
                    "Provide at least one updatable field in the payload."
                ]
            }
            return False

        unexpected_fields = sorted(
            set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        self.validated_data = {
            "doc_type": self.initial_data.get("doc_type", self.instance.doc_type),
            "is_generated": self.initial_data.get(
                "is_generated", self.instance.is_generated
            ),
            "doc_subtype": self.initial_data.get(
                "doc_subtype", self.instance.doc_subtype
            ),
            "source_url": self.initial_data.get("source_url", self.instance.source_url),
            "ocr_status": self.initial_data.get("ocr_status", self.instance.ocr_status),
            "extracted_text": self.initial_data.get(
                "extracted_text", self.instance.extracted_text
            ),
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
            update_fields=["doc_type", "is_generated", "doc_subtype", "source_url",
                           "ocr_status", "extracted_text", "updated_at"]
        )
        return self.instance


# ---------------------------------------------------------------------------
# Signal serializers
# ---------------------------------------------------------------------------

def serialize_signal(signal: Signal) -> dict:
    from .signal_rules import RULE_REGISTRY
    rule = RULE_REGISTRY.get(signal.rule_id)
    return {
        "id": str(signal.pk),
        "rule_id": signal.rule_id,
        "severity": signal.severity,
        "status": signal.status,
        "title": rule.title if rule else signal.rule_id,
        "description": rule.description if rule else "",
        "detected_summary": signal.detected_summary,
        "trigger_entity_id": (
            str(signal.trigger_entity_id) if signal.trigger_entity_id else None
        ),
        "trigger_doc_id": (
            str(signal.trigger_doc_id) if signal.trigger_doc_id else None
        ),
        "investigator_note": signal.investigator_note,
        "detected_at": _serialize_datetime(signal.detected_at),
    }


_VALID_SIGNAL_STATUSES = {
    SignalStatus.OPEN,
    SignalStatus.CONFIRMED,
    SignalStatus.DISMISSED,
    SignalStatus.ESCALATED,
}


class SignalUpdateSerializer:
    """
    Validates PATCH payloads for a Signal instance.

    Allowed fields: ``status``, ``investigator_note``.
    ``investigator_note`` is required when status is DISMISSED so that there is
    always a documented rationale (FR-604).
    """

    allowed_fields = {"status", "investigator_note"}

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
        return serialize_signal(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": [
                "A signal instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {
                "non_field_errors": [
                    "Provide at least one updatable field in the payload."
                ]
            }
            return False

        unexpected_fields = sorted(
            set(self.initial_data.keys()) - self.allowed_fields
        )
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [
                    f"Unexpected field(s): {', '.join(unexpected_fields)}"
                ]
            }
            return False

        new_status = self.initial_data.get("status", self.instance.status)
        if new_status not in _VALID_SIGNAL_STATUSES:
            valid_list = ", ".join(sorted(_VALID_SIGNAL_STATUSES))
            self._errors = {
                "status": [
                    f"Invalid status. Expected one of: {valid_list}."
                ]
            }
            return False

        new_note = self.initial_data.get(
            "investigator_note", self.instance.investigator_note
        )

        if new_status == SignalStatus.DISMISSED and not (new_note or "").strip():
            self._errors = {
                "investigator_note": [
                    "A dismissal rationale is required when setting status to DISMISSED."
                ]
            }
            return False

        self.validated_data = {
            "status": new_status,
            "investigator_note": new_note or "",
        }
        return True

    def save(self) -> Signal:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance.status = self.validated_data["status"]
        self.instance.investigator_note = self.validated_data["investigator_note"]
        self.instance.save(update_fields=["status", "investigator_note"])
        return self.instance
