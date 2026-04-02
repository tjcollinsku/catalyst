import re

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Case,
    Detection,
    DetectionStatus,
    Document,
    Finding,
    FindingConfidence,
    FindingDocument,
    FindingEntity,
    FindingSeverity,
    FindingStatus,
    GovernmentReferral,
    ReferralStatus,
    Signal,
    SignalStatus,
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
        "trigger_entity_id": (str(signal.trigger_entity_id) if signal.trigger_entity_id else None),
        "trigger_doc_id": (str(signal.trigger_doc_id) if signal.trigger_doc_id else None),
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
            self._errors = {"non_field_errors": ["A signal instance is required."]}
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

        new_status = self.initial_data.get("status", self.instance.status)
        if new_status not in _VALID_SIGNAL_STATUSES:
            valid_list = ", ".join(sorted(_VALID_SIGNAL_STATUSES))
            self._errors = {"status": [f"Invalid status. Expected one of: {valid_list}."]}
            return False

        new_note = self.initial_data.get("investigator_note", self.instance.investigator_note)

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


# ---------------------------------------------------------------------------
# Detection serializers
# ---------------------------------------------------------------------------


def serialize_detection(detection: Detection) -> dict:
    return {
        "id": str(detection.pk),
        "case_id": str(detection.case_id),
        "signal_type": detection.signal_type,
        "severity": detection.severity,
        "status": detection.status,
        "detection_method": detection.detection_method,
        "primary_document_id": (
            str(detection.primary_document_id) if detection.primary_document_id else None
        ),
        "secondary_document_id": (
            str(detection.secondary_document_id) if detection.secondary_document_id else None
        ),
        "person_id": str(detection.person_id) if detection.person_id else None,
        "organization_id": (str(detection.organization_id) if detection.organization_id else None),
        "property_record_id": (
            str(detection.property_record_id) if detection.property_record_id else None
        ),
        "financial_instrument_id": (
            str(detection.financial_instrument_id) if detection.financial_instrument_id else None
        ),
        "evidence_snapshot": detection.evidence_snapshot,
        "confidence_score": detection.confidence_score,
        "investigator_note": detection.investigator_note,
        "detected_at": _serialize_datetime(detection.detected_at),
        "reviewed_at": _serialize_datetime(detection.reviewed_at),
        "reviewed_by": detection.reviewed_by,
    }


_VALID_DETECTION_STATUSES = {s.value for s in DetectionStatus}


class DetectionIntakeSerializer:
    """Validates POST payloads for creating a Detection (investigator-manual path)."""

    allowed_fields = {
        "signal_type",
        "severity",
        "primary_document_id",
        "secondary_document_id",
        "person_id",
        "organization_id",
        "property_record_id",
        "financial_instrument_id",
        "evidence_snapshot",
        "confidence_score",
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
        return serialize_detection(self.instance)

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

        signal_type = (self.initial_data.get("signal_type") or "").strip()
        valid_signal_types = {c[0] for c in Detection._meta.get_field("signal_type").choices}
        if signal_type not in valid_signal_types:
            self._errors = {
                "signal_type": [
                    f"Invalid signal_type. Expected one of: "
                    f"{', '.join(sorted(valid_signal_types))}."
                ]
            }
            return False

        severity = (self.initial_data.get("severity") or "").strip()
        valid_severities = {c[0] for c in Detection._meta.get_field("severity").choices}
        if severity not in valid_severities:
            self._errors = {
                "severity": [
                    f"Invalid severity. Expected one of: {', '.join(sorted(valid_severities))}."
                ]
            }
            return False

        confidence_score = self.initial_data.get("confidence_score", 1.0)
        try:
            confidence_score = float(confidence_score)
            if not (0.0 <= confidence_score <= 1.0):
                raise ValueError
        except (TypeError, ValueError):
            self._errors = {"confidence_score": ["Must be a float between 0.0 and 1.0."]}
            return False

        self.validated_data = {
            "signal_type": signal_type,
            "severity": severity,
            "detection_method": "INVESTIGATOR_MANUAL",
            "primary_document_id": self.initial_data.get("primary_document_id") or None,
            "secondary_document_id": self.initial_data.get("secondary_document_id") or None,
            "person_id": self.initial_data.get("person_id") or None,
            "organization_id": self.initial_data.get("organization_id") or None,
            "property_record_id": self.initial_data.get("property_record_id") or None,
            "financial_instrument_id": self.initial_data.get("financial_instrument_id") or None,
            "evidence_snapshot": self.initial_data.get("evidence_snapshot") or {},
            "confidence_score": confidence_score,
            "investigator_note": (self.initial_data.get("investigator_note") or "").strip(),
        }
        return True

    def save(self) -> Detection:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance = Detection.objects.create(case=self.case, **self.validated_data)
        return self.instance


class DetectionUpdateSerializer:
    """Validates PATCH payloads for updating a Detection's status and note."""

    allowed_fields = {"status", "investigator_note", "reviewed_by", "confidence_score"}

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
        return serialize_detection(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": ["A detection instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {"non_field_errors": ["Provide at least one updatable field."]}
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        new_status = self.initial_data.get("status", self.instance.status)
        if new_status not in _VALID_DETECTION_STATUSES:
            self._errors = {
                "status": [
                    f"Invalid status. Expected one of: "
                    f"{', '.join(sorted(_VALID_DETECTION_STATUSES))}."
                ]
            }
            return False

        new_note = self.initial_data.get("investigator_note", self.instance.investigator_note)
        if new_status == DetectionStatus.DISMISSED and not (new_note or "").strip():
            self._errors = {
                "investigator_note": [
                    "A dismissal rationale is required when setting status to DISMISSED."
                ]
            }
            return False

        confidence_score = self.initial_data.get("confidence_score", self.instance.confidence_score)
        try:
            confidence_score = float(confidence_score)
            if not (0.0 <= confidence_score <= 1.0):
                raise ValueError
        except (TypeError, ValueError):
            self._errors = {"confidence_score": ["Must be a float between 0.0 and 1.0."]}
            return False

        self.validated_data = {
            "status": new_status,
            "investigator_note": new_note or "",
            "reviewed_by": (self.initial_data.get("reviewed_by", self.instance.reviewed_by) or ""),
            "confidence_score": confidence_score,
        }
        return True

    def save(self) -> Detection:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        from django.utils import timezone as tz

        self.instance.status = self.validated_data["status"]
        self.instance.investigator_note = self.validated_data["investigator_note"]
        self.instance.reviewed_by = self.validated_data["reviewed_by"]
        self.instance.confidence_score = self.validated_data["confidence_score"]
        update_fields = ["status", "investigator_note", "reviewed_by", "confidence_score"]
        if self.validated_data["status"] in (
            DetectionStatus.REVIEWED,
            DetectionStatus.CONFIRMED,
            DetectionStatus.DISMISSED,
            DetectionStatus.ESCALATED,
        ):
            self.instance.reviewed_at = tz.now()
            update_fields.append("reviewed_at")
        self.instance.save(update_fields=update_fields)
        return self.instance


# ---------------------------------------------------------------------------
# GovernmentReferral serializers
# ---------------------------------------------------------------------------

_VALID_REFERRAL_STATUSES = {s.value for s in ReferralStatus}


def serialize_referral(referral: GovernmentReferral) -> dict:
    return {
        "referral_id": referral.referral_id,
        "case_id": str(referral.case_id) if referral.case_id else None,
        "agency_name": referral.agency_name or "",
        "submission_id": referral.submission_id or "",
        "contact_alias": referral.contact_alias or "",
        "status": referral.status,
        "notes": referral.notes,
        "filing_date": _serialize_datetime(referral.filing_date),
    }


class ReferralIntakeSerializer:
    allowed_fields = {"agency_name", "submission_id", "contact_alias", "notes"}

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
        return serialize_referral(self.instance)

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

        agency_name = (self.initial_data.get("agency_name") or "").strip()
        if not agency_name:
            self._errors = {"agency_name": ["Agency name is required."]}
            return False

        self.validated_data = {
            "agency_name": agency_name,
            "submission_id": (self.initial_data.get("submission_id") or "").strip() or None,
            "contact_alias": (self.initial_data.get("contact_alias") or "").strip() or None,
            "notes": (self.initial_data.get("notes") or "").strip(),
        }
        return True

    def save(self) -> GovernmentReferral:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        self.instance = GovernmentReferral.objects.create(
            case=self.case,
            status=ReferralStatus.DRAFT,
            **self.validated_data,
        )
        return self.instance


class ReferralUpdateSerializer:
    allowed_fields = {"agency_name", "submission_id", "contact_alias", "notes", "status"}

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
        return serialize_referral(self.instance)

    def is_valid(self) -> bool:
        self._errors = {}
        self.validated_data = {}

        if self.instance is None:
            self._errors = {"non_field_errors": ["A referral instance is required."]}
            return False

        if not isinstance(self.initial_data, dict):
            self._errors = {"non_field_errors": ["Expected a JSON object."]}
            return False

        if not self.initial_data:
            self._errors = {"non_field_errors": ["Provide at least one updatable field."]}
            return False

        unexpected_fields = sorted(set(self.initial_data.keys()) - self.allowed_fields)
        if unexpected_fields:
            self._errors = {
                "non_field_errors": [f"Unexpected field(s): {', '.join(unexpected_fields)}"]
            }
            return False

        new_status = self.initial_data.get("status", self.instance.status)
        if new_status not in _VALID_REFERRAL_STATUSES:
            self._errors = {
                "status": [
                    f"Invalid status. Expected one of: "
                    f"{', '.join(sorted(_VALID_REFERRAL_STATUSES))}."
                ]
            }
            return False

        self.validated_data = {
            "agency_name": (
                self.initial_data.get("agency_name", self.instance.agency_name) or ""
            ).strip()
            or self.instance.agency_name,
            "submission_id": self.initial_data.get("submission_id", self.instance.submission_id),
            "contact_alias": self.initial_data.get("contact_alias", self.instance.contact_alias),
            "notes": self.initial_data.get("notes", self.instance.notes),
            "status": new_status,
        }
        return True

    def save(self) -> GovernmentReferral:
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        for field, value in self.validated_data.items():
            setattr(self.instance, field, value)
        self.instance.save(
            update_fields=["agency_name", "submission_id", "contact_alias", "notes", "status"]
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
        "name": f"{fi.instrument_type} {fi.filing_number or ''}" .strip() or str(fi.pk)[:8],
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
    from .models import InvestigatorNote

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

        self.instance = InvestigatorNote.objects.create(
            case=self.case, **self.validated_data
        )
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

_VALID_FINDING_SEVERITIES = {c.value for c in FindingSeverity}
_VALID_FINDING_CONFIDENCES = {c.value for c in FindingConfidence}
_VALID_FINDING_STATUSES = {c.value for c in FindingStatus}


def serialize_finding(finding):
    """Serialize a Finding model instance to a plain dict."""
    return {
        "id": str(finding.pk),
        "case_id": str(finding.case_id),
        "detection_id": str(finding.detection_id) if finding.detection_id else None,
        "title": finding.title,
        "narrative": finding.narrative,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status,
        "signal_type": finding.signal_type,
        "signal_rule_id": finding.signal_rule_id,
        "legal_refs": finding.legal_refs,
        "created_at": _serialize_datetime(finding.created_at),
        "updated_at": _serialize_datetime(finding.updated_at),
        "entity_links": [
            {
                "id": str(el.pk),
                "entity_id": str(el.entity_id),
                "entity_type": el.entity_type,
                "context_note": el.context_note or "",
            }
            for el in finding.entity_links.all()
        ],
        "document_links": [
            {
                "id": str(dl.pk),
                "document_id": str(dl.document_id),
                "page_reference": dl.page_reference or "",
                "context_note": dl.context_note or "",
            }
            for dl in finding.document_links.all()
        ],
    }


class FindingIntakeSerializer:
    """Validates data for creating a new Finding."""

    _ALLOWED_FIELDS = {
        "title", "narrative", "severity", "confidence", "status",
        "signal_type", "signal_rule_id", "legal_refs", "detection_id",
    }

    def __init__(self, data: dict, case):
        self.initial_data = data
        self.case = case
        self.errors: dict[str, list[str]] = {}
        self.validated_data: dict = {}

    def is_valid(self) -> bool:
        data = self.initial_data
        errors: dict[str, list[str]] = {}

        # Reject unexpected fields
        extra = set(data.keys()) - self._ALLOWED_FIELDS
        if extra:
            errors["__all__"] = [f"Unexpected fields: {', '.join(sorted(extra))}."]

        # title — required
        title = data.get("title", "")
        if isinstance(title, str):
            title = title.strip()
        if not title:
            errors["title"] = ["Title is required."]

        # narrative — required
        narrative = data.get("narrative", "")
        if isinstance(narrative, str):
            narrative = narrative.strip()
        if not narrative:
            errors["narrative"] = ["Narrative is required."]

        # severity — optional, validate against choices
        severity = data.get("severity", FindingSeverity.MEDIUM)
        if severity not in _VALID_FINDING_SEVERITIES:
            errors["severity"] = [
                f"Invalid severity. Expected one of: {', '.join(sorted(_VALID_FINDING_SEVERITIES))}."
            ]

        # confidence — optional
        confidence = data.get("confidence", FindingConfidence.POSSIBLE)
        if confidence not in _VALID_FINDING_CONFIDENCES:
            errors["confidence"] = [
                f"Invalid confidence. Expected one of: {', '.join(sorted(_VALID_FINDING_CONFIDENCES))}."
            ]

        # status — optional
        status = data.get("status", FindingStatus.DRAFT)
        if status not in _VALID_FINDING_STATUSES:
            errors["status"] = [
                f"Invalid status. Expected one of: {', '.join(sorted(_VALID_FINDING_STATUSES))}."
            ]

        # legal_refs — optional, must be a list of strings
        legal_refs = data.get("legal_refs", [])
        if not isinstance(legal_refs, list) or not all(isinstance(r, str) for r in legal_refs):
            errors["legal_refs"] = ["legal_refs must be a list of strings."]

        # detection_id — optional UUID
        detection_id = data.get("detection_id")
        if detection_id is not None:
            import uuid as _uuid
            try:
                detection_id = str(_uuid.UUID(str(detection_id)))
            except (ValueError, AttributeError):
                errors["detection_id"] = ["Invalid UUID for detection_id."]

        if errors:
            self.errors = errors
            return False

        self.validated_data = {
            "case": self.case,
            "title": title,
            "narrative": narrative,
            "severity": severity,
            "confidence": confidence,
            "status": status,
            "signal_type": data.get("signal_type", ""),
            "signal_rule_id": data.get("signal_rule_id", ""),
            "legal_refs": legal_refs,
            "detection_id": detection_id,
        }
        return True

    @property
    def data(self):
        return self.validated_data

    def save(self):
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        return Finding.objects.create(**self.validated_data)


class FindingUpdateSerializer:
    """Validates data for patching an existing Finding."""

    _ALLOWED_FIELDS = {
        "title", "narrative", "severity", "confidence", "status",
        "signal_type", "signal_rule_id", "legal_refs", "detection_id",
    }

    def __init__(self, data: dict, instance: Finding):
        self.initial_data = data
        self.instance = instance
        self.errors: dict[str, list[str]] = {}
        self.validated_data: dict = {}

    def is_valid(self) -> bool:
        data = self.initial_data
        errors: dict[str, list[str]] = {}

        extra = set(data.keys()) - self._ALLOWED_FIELDS
        if extra:
            errors["__all__"] = [f"Unexpected fields: {', '.join(sorted(extra))}."]

        if not data:
            errors["__all__"] = ["Request body must contain at least one field to update."]

        update_fields = {}

        if "title" in data:
            title = data["title"]
            if isinstance(title, str):
                title = title.strip()
            if not title:
                errors["title"] = ["Title cannot be empty."]
            else:
                update_fields["title"] = title

        if "narrative" in data:
            narrative = data["narrative"]
            if isinstance(narrative, str):
                narrative = narrative.strip()
            if not narrative:
                errors["narrative"] = ["Narrative cannot be empty."]
            else:
                update_fields["narrative"] = narrative

        if "severity" in data:
            if data["severity"] not in _VALID_FINDING_SEVERITIES:
                errors["severity"] = [
                    f"Invalid severity. Expected one of: {', '.join(sorted(_VALID_FINDING_SEVERITIES))}."
                ]
            else:
                update_fields["severity"] = data["severity"]

        if "confidence" in data:
            if data["confidence"] not in _VALID_FINDING_CONFIDENCES:
                errors["confidence"] = [
                    f"Invalid confidence. Expected one of: {', '.join(sorted(_VALID_FINDING_CONFIDENCES))}."
                ]
            else:
                update_fields["confidence"] = data["confidence"]

        if "status" in data:
            if data["status"] not in _VALID_FINDING_STATUSES:
                errors["status"] = [
                    f"Invalid status. Expected one of: {', '.join(sorted(_VALID_FINDING_STATUSES))}."
                ]
            else:
                update_fields["status"] = data["status"]

        if "signal_type" in data:
            update_fields["signal_type"] = data["signal_type"]

        if "signal_rule_id" in data:
            update_fields["signal_rule_id"] = data["signal_rule_id"]

        if "legal_refs" in data:
            lr = data["legal_refs"]
            if not isinstance(lr, list) or not all(isinstance(r, str) for r in lr):
                errors["legal_refs"] = ["legal_refs must be a list of strings."]
            else:
                update_fields["legal_refs"] = lr

        if "detection_id" in data:
            det_id = data["detection_id"]
            if det_id is not None:
                import uuid as _uuid
                try:
                    det_id = str(_uuid.UUID(str(det_id)))
                except (ValueError, AttributeError):
                    errors["detection_id"] = ["Invalid UUID for detection_id."]
            update_fields["detection_id"] = det_id

        if errors:
            self.errors = errors
            return False

        self.validated_data = update_fields
        return True

    @property
    def data(self):
        return self.validated_data

    def save(self):
        if not self.validated_data:
            raise ValueError("Call is_valid() before save().")
        for key, value in self.validated_data.items():
            setattr(self.instance, key, value)
        self.instance.updated_at = timezone.now()
        fields_to_save = list(self.validated_data.keys()) + ["updated_at"]
        self.instance.save(update_fields=fields_to_save)
        return self.instance
