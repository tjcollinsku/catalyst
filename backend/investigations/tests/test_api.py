import json
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Case, Document, DocumentType, OcrStatus


class CaseIntakeApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_create_case_accepts_valid_payload(self):
        response = self.client.post(
            reverse("api_case_collection"),
            data=json.dumps(
                {
                    "name": "Example Township Intake",
                    "status": "ACTIVE",
                    "notes": "Initial field intake.",
                    "referral_ref": "IC3-78A987D4",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Example Township Intake")
        self.assertEqual(payload["status"], "ACTIVE")
        self.assertEqual(Case.objects.count(), 1)

    def test_create_case_rejects_invalid_payload(self):
        response = self.client.post(
            reverse("api_case_collection"),
            data=json.dumps({"name": "", "status": "INVALID"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("name", payload["errors"])
        self.assertIn("status", payload["errors"])

    def test_case_detail_includes_document_metadata(self):
        case = Case.objects.create(name="Referral Case")
        document = Document.objects.create(
            case=case,
            filename="packet.pdf",
            file_path="cases/test/packet.pdf",
            sha256_hash="a" * 64,
            file_size=2048,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.COMPLETED,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(reverse("api_case_detail", args=[case.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(case.pk))
        self.assertEqual(len(payload["documents"]), 1)
        self.assertEqual(payload["documents"][0]["id"], str(document.pk))
        self.assertEqual(payload["documents"][0]["filename"], "packet.pdf")

    def test_case_list_returns_newest_first(self):
        older = Case.objects.create(name="Older Case")
        newer = Case.objects.create(name="Newer Case")

        response = self.client.get(reverse("api_case_collection"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["limit"], 25)
        self.assertEqual(payload["offset"], 0)
        self.assertIsNone(payload["next_offset"])
        self.assertIsNone(payload["previous_offset"])
        self.assertEqual(
            [item["id"] for item in payload["results"]],
            [str(newer.pk), str(older.pk)],
        )

    def test_case_list_respects_limit_and_offset(self):
        oldest = Case.objects.create(name="Oldest Case")
        middle = Case.objects.create(name="Middle Case")
        newest = Case.objects.create(name="Newest Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"limit": "1", "offset": "1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["offset"], 1)
        self.assertEqual(payload["next_offset"], 2)
        self.assertEqual(payload["previous_offset"], 0)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["id"], str(middle.pk))
        self.assertNotEqual(payload["results"][0]["id"], str(newest.pk))
        self.assertNotEqual(payload["results"][0]["id"], str(oldest.pk))

    def test_case_list_rejects_invalid_pagination_params(self):
        Case.objects.create(name="Validation Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"limit": "bad", "offset": "-1"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_case_list_filters_by_status_and_name_query(self):
        Case.objects.create(name="Example Township Active", status="ACTIVE")
        Case.objects.create(name="Example Township Paused", status="PAUSED")
        Case.objects.create(name="Other Active", status="ACTIVE")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"status": "ACTIVE", "q": "example_township"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["name"], "Example Township Active")

    def test_case_list_rejects_invalid_status_filter(self):
        Case.objects.create(name="Status Filter Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"status": "NOT_A_STATUS"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("status", payload["errors"])

    def test_case_list_filters_by_created_date_range(self):
        old_case = Case.objects.create(
            name="Old Range Case",
            created_at=timezone.now() - timedelta(days=10),
        )
        in_range_case = Case.objects.create(
            name="In Range Case",
            created_at=timezone.now() - timedelta(days=2),
        )

        response = self.client.get(
            reverse("api_case_collection"),
            data={"created_from": (
                timezone.now() - timedelta(days=5)).date().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["results"]]
        self.assertIn(str(in_range_case.pk), ids)
        self.assertNotIn(str(old_case.pk), ids)

    def test_case_list_rejects_invalid_created_date_filter(self):
        Case.objects.create(name="Date Validation Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"created_from": "not-a-date"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("created_from", payload["errors"])

    def test_case_list_rejects_inverted_created_date_range(self):
        Case.objects.create(name="Inverted Range Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"created_from": "2026-03-27", "created_to": "2026-03-01"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_delete_case_returns_204_when_no_related_records(self):
        case = Case.objects.create(name="Deletable Case")

        response = self.client.delete(
            reverse("api_case_detail", args=[case.pk]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Case.objects.filter(pk=case.pk).exists())

    def test_delete_case_returns_409_when_related_records_exist(self):
        case = Case.objects.create(name="Protected Delete Case")
        Document.objects.create(
            case=case,
            filename="protected.pdf",
            file_path="cases/doc/protected.pdf",
            sha256_hash="4" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.delete(
            reverse("api_case_detail", args=[case.pk]))

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_case_list_order_is_deterministic_for_timestamp_ties(self):
        shared_created_at = timezone.now()
        first = Case.objects.create(
            name="Tie Case 1", created_at=shared_created_at)
        second = Case.objects.create(
            name="Tie Case 2", created_at=shared_created_at)

        response = self.client.get(reverse("api_case_collection"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        expected_ids = sorted([str(first.pk), str(second.pk)], reverse=True)
        self.assertEqual([item["id"]
                         for item in payload["results"]], expected_ids)

    def test_case_list_supports_custom_sort(self):
        z_case = Case.objects.create(name="Zulu Case")
        a_case = Case.objects.create(name="Alpha Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"order_by": "name", "direction": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["results"]]
        self.assertTrue(ids.index(str(a_case.pk)) < ids.index(str(z_case.pk)))

    def test_case_list_rejects_invalid_sort_params(self):
        Case.objects.create(name="Sort Validation Case")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"order_by": "not_a_field", "direction": "sideways"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("order_by", payload["errors"])

    def test_create_document_accepts_valid_payload(self):
        case = Case.objects.create(name="Document Case")
        response = self.client.post(
            reverse("api_case_document_collection", args=[case.pk]),
            data=json.dumps(
                {
                    "filename": "referral.pdf",
                    "file_path": "cases/doc/referral.pdf",
                    "sha256_hash": "b" * 64,
                    "file_size": 4096,
                    "doc_type": "OTHER",
                    "source_url": "https://example.org/referral",
                    "ocr_status": "PENDING",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["filename"], "referral.pdf")
        self.assertEqual(payload["doc_type"], "OTHER")
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Document.objects.first().case_id, case.pk)

    def test_create_document_rejects_invalid_payload(self):
        case = Case.objects.create(name="Bad Document Case")
        response = self.client.post(
            reverse("api_case_document_collection", args=[case.pk]),
            data=json.dumps(
                {
                    "filename": "",
                    "file_path": "cases/doc/bad.pdf",
                    "sha256_hash": "0" * 64,
                    "file_size": -5,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("filename", payload["errors"])

    def test_create_document_rejects_invalid_sha256_hash(self):
        case = Case.objects.create(name="Invalid Hash Case")
        response = self.client.post(
            reverse("api_case_document_collection", args=[case.pk]),
            data=json.dumps(
                {
                    "filename": "bad-hash.pdf",
                    "file_path": "cases/doc/bad-hash.pdf",
                    "sha256_hash": "not-a-valid-hash",
                    "file_size": 100,
                    "doc_type": "OTHER",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("sha256_hash", payload["errors"])

    def test_create_document_returns_404_for_missing_case(self):
        response = self.client.post(
            reverse("api_case_document_collection", args=[uuid.uuid4()]),
            data=json.dumps(
                {
                    "filename": "orphan.pdf",
                    "file_path": "cases/orphan.pdf",
                    "sha256_hash": "c" * 64,
                    "file_size": 128,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_list_case_documents_returns_newest_first(self):
        case = Case.objects.create(name="Document Listing Case")
        older = Document.objects.create(
            case=case,
            filename="older.pdf",
            file_path="cases/doc/older.pdf",
            sha256_hash="e" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(days=1),
        )
        newer = Document.objects.create(
            case=case,
            filename="newer.pdf",
            file_path="cases/doc/newer.pdf",
            sha256_hash="f" * 64,
            file_size=200,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["limit"], 25)
        self.assertEqual(payload["offset"], 0)
        self.assertIsNone(payload["next_offset"])
        self.assertIsNone(payload["previous_offset"])
        self.assertEqual(
            [item["id"] for item in payload["results"]],
            [str(newer.pk), str(older.pk)],
        )

    def test_list_case_documents_respects_limit_and_offset(self):
        case = Case.objects.create(name="Document Pagination Case")
        oldest = Document.objects.create(
            case=case,
            filename="oldest.pdf",
            file_path="cases/doc/oldest.pdf",
            sha256_hash="1" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now() - timedelta(days=2),
            updated_at=timezone.now() - timedelta(days=2),
        )
        middle = Document.objects.create(
            case=case,
            filename="middle.pdf",
            file_path="cases/doc/middle.pdf",
            sha256_hash="2" * 64,
            file_size=200,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(days=1),
        )
        newest = Document.objects.create(
            case=case,
            filename="newest.pdf",
            file_path="cases/doc/newest.pdf",
            sha256_hash="3" * 64,
            file_size=300,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"limit": "1", "offset": "1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["offset"], 1)
        self.assertEqual(payload["next_offset"], 2)
        self.assertEqual(payload["previous_offset"], 0)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["id"], str(middle.pk))
        self.assertNotEqual(payload["results"][0]["id"], str(newest.pk))
        self.assertNotEqual(payload["results"][0]["id"], str(oldest.pk))

    def test_list_case_documents_rejects_invalid_pagination_params(self):
        case = Case.objects.create(name="Invalid Pagination Case")

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"limit": "0", "offset": "-1"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_list_case_documents_filters_by_doc_type_and_ocr_status(self):
        case = Case.objects.create(name="Filtered Documents Case")
        Document.objects.create(
            case=case,
            filename="match.pdf",
            file_path="cases/doc/match.pdf",
            sha256_hash="a" * 64,
            file_size=100,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.COMPLETED,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )
        Document.objects.create(
            case=case,
            filename="wrong-type.pdf",
            file_path="cases/doc/wrong-type.pdf",
            sha256_hash="b" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.COMPLETED,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )
        Document.objects.create(
            case=case,
            filename="wrong-status.pdf",
            file_path="cases/doc/wrong-status.pdf",
            sha256_hash="c" * 64,
            file_size=100,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"doc_type": "DEED", "ocr_status": "COMPLETED"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["filename"], "match.pdf")

    def test_list_case_documents_rejects_invalid_filter_values(self):
        case = Case.objects.create(name="Bad Filter Case")

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"doc_type": "NOT_A_TYPE", "ocr_status": "NOT_A_STATUS"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("doc_type", payload["errors"])

    def test_list_case_documents_filters_by_uploaded_date_range(self):
        case = Case.objects.create(name="Date Filter Documents Case")
        old_document = Document.objects.create(
            case=case,
            filename="old.pdf",
            file_path="cases/doc/old.pdf",
            sha256_hash="a" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now() - timedelta(days=15),
            updated_at=timezone.now() - timedelta(days=15),
        )
        new_document = Document.objects.create(
            case=case,
            filename="new.pdf",
            file_path="cases/doc/new.pdf",
            sha256_hash="b" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"uploaded_from": (
                timezone.now() - timedelta(days=5)).date().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["results"]]
        self.assertIn(str(new_document.pk), ids)
        self.assertNotIn(str(old_document.pk), ids)

    def test_list_case_documents_rejects_invalid_uploaded_date_filter(self):
        case = Case.objects.create(name="Invalid Uploaded Date Case")

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"uploaded_from": "invalid-date"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("uploaded_from", payload["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
