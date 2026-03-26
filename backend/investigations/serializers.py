from django.core.exceptions import ValidationError
from django.utils import timezone
import re

from .models import Case, Document


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
    allowed_fields = {"doc_type", "source_url", "ocr_status", "extracted_text"}

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
            update_fields=["doc_type", "source_url",
                           "ocr_status", "extracted_text", "updated_at"]
        )
        return self.instance
