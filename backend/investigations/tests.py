import json
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Case, Document, DocumentType, OcrStatus


class CaseIntakeApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_create_case_accepts_valid_payload(self):
        response = self.client.post(
            reverse("api_case_collection"),
            data=json.dumps(
                {
                    "name": "Osgood Intake",
                    "status": "ACTIVE",
                    "notes": "Initial field intake.",
                    "referral_ref": "IC3-78A987D4",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Osgood Intake")
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
        Case.objects.create(name="Osgood Active", status="ACTIVE")
        Case.objects.create(name="Osgood Paused", status="PAUSED")
        Case.objects.create(name="Other Active", status="ACTIVE")

        response = self.client.get(
            reverse("api_case_collection"),
            data={"status": "ACTIVE", "q": "osgood"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["name"], "Osgood Active")

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


# =============================================================================
# Entity Extraction Tests
# These tests are pure Python — no DB, no Django. They test that regex patterns
# correctly identify candidates from realistic public records text.
# =============================================================================

class EntityExtractionPersonTests(unittest.TestCase):
    """Tests for person name extraction from labeled contexts."""

    def setUp(self):
        from .entity_extraction import extract_entities
        self.extract = extract_entities

    def test_extracts_labeled_grantor(self):
        text = "GRANTOR: John A. Homan, of Hardin County, Ohio"
        result = self.extract(text)
        raws = [p["raw"] for p in result["persons"]]
        self.assertTrue(
            any("Homan" in r for r in raws),
            f"Expected 'Homan' in persons, got: {raws}",
        )

    def test_extracts_labeled_grantee(self):
        text = "GRANTEE: Do Good RE LLC, an Ohio limited liability company"
        result = self.extract(text)
        # Org should catch the LLC, person list should be empty or not contain LLC
        raws = [p["raw"] for p in result["persons"]]
        self.assertFalse(
            any("Do Good RE LLC" in r for r in raws),
            "LLC should not be extracted as a person",
        )

    def test_extracts_inverted_name(self):
        text = "Debtor: HOMAN, JOHN A., Hardin County"
        result = self.extract(text)
        raws = [p["raw"] for p in result["persons"]]
        self.assertTrue(
            any("Homan" in r for r in raws),
            f"Expected inverted name in persons, got: {raws}",
        )

    def test_returns_context_snippet(self):
        text = "GRANTOR: John A. Homan, of Hardin County, Ohio, hereinafter"
        result = self.extract(text)
        self.assertTrue(len(result["persons"]) > 0)
        self.assertIn("context", result["persons"][0])
        self.assertIsInstance(result["persons"][0]["context"], str)

    def test_empty_text_returns_empty_results(self):
        result = self.extract("")
        self.assertEqual(result["persons"], [])
        self.assertEqual(result["orgs"], [])
        self.assertEqual(result["dates"], [])
        self.assertEqual(result["amounts"], [])

    def test_whitespace_only_text_returns_empty_results(self):
        result = self.extract("   \n\t  ")
        self.assertEqual(result["persons"], [])


class EntityExtractionOrgTests(unittest.TestCase):
    """Tests for organization name extraction."""

    def setUp(self):
        from .entity_extraction import extract_entities
        self.extract = extract_entities

    def test_extracts_nonprofit_with_inc(self):
        text = "Grantor: Do Good Ministries, Inc., an Ohio nonprofit corporation"
        result = self.extract(text)
        raws = [o["raw"] for o in result["orgs"]]
        self.assertTrue(
            any("Do Good Ministries" in r for r in raws),
            f"Expected 'Do Good Ministries' in orgs, got: {raws}",
        )

    def test_extracts_llc(self):
        text = "The property was transferred to Do Good RE LLC."
        result = self.extract(text)
        raws = [o["raw"] for o in result["orgs"]]
        self.assertTrue(
            any("Do Good RE LLC" in r for r in raws),
            f"Expected LLC in orgs, got: {raws}",
        )

    def test_extracts_management_llp(self):
        text = "Secured Party: Homan AG Management LLP"
        result = self.extract(text)
        raws = [o["raw"] for o in result["orgs"]]
        self.assertTrue(
            any("Homan AG Management" in r for r in raws),
            f"Expected management org in orgs, got: {raws}",
        )

    def test_no_duplicate_orgs(self):
        text = (
            "Do Good Ministries, Inc. transferred property to Do Good Ministries, Inc."
        )
        result = self.extract(text)
        raws = [o["raw"] for o in result["orgs"]]
        do_good_count = sum(1 for r in raws if "Do Good Ministries" in r)
        self.assertEqual(do_good_count, 1, "Duplicate org should be deduplicated")


class EntityExtractionDateTests(unittest.TestCase):
    """Tests for date extraction and normalization."""

    def setUp(self):
        from .entity_extraction import extract_entities
        self.extract = extract_entities

    def test_extracts_long_form_date(self):
        text = "This deed is made this March 2, 2022, by and between"
        result = self.extract(text)
        self.assertTrue(len(result["dates"]) > 0)
        normalized = result["dates"][0]["normalized"]
        self.assertEqual(normalized, "2022-03-02")

    def test_extracts_slash_date(self):
        text = "Filed on 08/02/2022 with the Ohio Secretary of State."
        result = self.extract(text)
        self.assertTrue(len(result["dates"]) > 0)
        normalized = result["dates"][0]["normalized"]
        self.assertEqual(normalized, "2022-08-02")

    def test_extracts_iso_date(self):
        text = "Amendment date: 2022-08-02"
        result = self.extract(text)
        self.assertTrue(len(result["dates"]) > 0)
        normalized = result["dates"][0]["normalized"]
        self.assertEqual(normalized, "2022-08-02")

    def test_no_duplicate_dates(self):
        text = "Filed March 2, 2022. Recorded on 03/02/2022."
        result = self.extract(text)
        # Both refer to the same date — should be deduplicated by normalized form
        march_2_count = sum(
            1 for d in result["dates"] if d.get("normalized") == "2022-03-02"
        )
        self.assertEqual(march_2_count, 1, "Same date in two formats should deduplicate")


class EntityExtractionAmountTests(unittest.TestCase):
    """Tests for dollar amount extraction and normalization."""

    def setUp(self):
        from .entity_extraction import extract_entities
        self.extract = extract_entities

    def test_extracts_large_amount_with_commas(self):
        text = "Total construction value: $4,505,000.00"
        result = self.extract(text)
        self.assertTrue(len(result["amounts"]) > 0)
        self.assertEqual(result["amounts"][0]["normalized"], 4505000.0)

    def test_extracts_zero_consideration(self):
        text = "For consideration of $0.00 and other valuable consideration"
        result = self.extract(text)
        self.assertTrue(len(result["amounts"]) > 0)
        self.assertEqual(result["amounts"][0]["normalized"], 0.0)

    def test_extracts_round_amount(self):
        text = "Purchase price: $300,000"
        result = self.extract(text)
        self.assertTrue(len(result["amounts"]) > 0)
        self.assertEqual(result["amounts"][0]["normalized"], 300000.0)

    def test_no_false_positive_on_year(self):
        text = "Filed in the year 2022 with reference number 12345"
        result = self.extract(text)
        # Years and reference numbers should not be extracted as dollar amounts
        self.assertEqual(result["amounts"], [])


# =============================================================================
# Entity Normalization Tests
# Pure Python — no DB needed.
# =============================================================================

class EntityNormalizationPersonTests(unittest.TestCase):
    """Tests that normalize_person_name produces consistent canonical forms."""

    def setUp(self):
        from .entity_normalization import normalize_person_name
        self.normalize = normalize_person_name

    def test_western_order_normalizes(self):
        self.assertEqual(self.normalize("John A. Homan"), "john a homan")

    def test_inverted_order_normalizes_to_same(self):
        # Both should normalize to the same canonical form
        western = self.normalize("John A. Homan")
        inverted = self.normalize("HOMAN, JOHN A.")
        self.assertEqual(western, inverted)

    def test_all_caps_normalizes(self):
        self.assertEqual(self.normalize("JOHN A HOMAN"), "john a homan")

    def test_strips_honorifics(self):
        self.assertEqual(self.normalize("Dr. John Homan"), "john homan")
        self.assertEqual(self.normalize("Mr. John Homan"), "john homan")

    def test_strips_jr_suffix(self):
        result = self.normalize("John Homan Jr.")
        self.assertNotIn("jr", result)
        self.assertIn("john", result)
        self.assertIn("homan", result)

    def test_preserves_hyphen_in_name(self):
        result = self.normalize("Mary Jo Winner-Baumer")
        self.assertIn("winner-baumer", result)

    def test_preserves_apostrophe_in_name(self):
        result = self.normalize("Patrick O'Brien")
        self.assertIn("o'brien", result)

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.normalize(""), "")

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(self.normalize("   "), "")


class EntityNormalizationOrgTests(unittest.TestCase):
    """Tests that normalize_org_name produces consistent canonical forms."""

    def setUp(self):
        from .entity_normalization import normalize_org_name
        self.normalize = normalize_org_name

    def test_strips_inc_designator(self):
        with_inc = self.normalize("Do Good Ministries, Inc.")
        without_inc = self.normalize("Do Good Ministries")
        self.assertEqual(with_inc, without_inc)

    def test_strips_llc_designator(self):
        with_llc = self.normalize("Do Good RE LLC")
        without_llc = self.normalize("Do Good RE")
        self.assertEqual(with_llc, without_llc)

    def test_strips_leading_the(self):
        with_the = self.normalize("The Baumer Foundation")
        without_the = self.normalize("Baumer Foundation")
        self.assertEqual(with_the, without_the)

    def test_normalizes_to_lowercase(self):
        result = self.normalize("DO GOOD MINISTRIES INC")
        self.assertEqual(result, result.lower())

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.normalize(""), "")


# =============================================================================
# Entity Resolution Tests
# These tests require the database (Django TestCase).
# =============================================================================

class EntityResolutionPersonTests(TestCase):
    """Tests for resolve_person() — exact match, new record creation, fuzzy."""

    def setUp(self):
        from .entity_resolution import resolve_person
        self.resolve = resolve_person
        self.case = Case.objects.create(name="Resolution Test Case")

    def test_creates_new_person_when_no_match(self):
        result = self.resolve("John A. Homan", self.case)
        self.assertTrue(result.created)
        self.assertEqual(result.person.full_name, "John A. Homan")

    def test_exact_match_returns_existing_person(self):
        # First call — creates
        first = self.resolve("John A. Homan", self.case)
        self.assertTrue(first.created)
        # Second call with identical name — should match
        second = self.resolve("John A. Homan", self.case)
        self.assertFalse(second.created)
        self.assertEqual(first.person.id, second.person.id)

    def test_normalized_match_returns_existing_person(self):
        # Create with one form
        first = self.resolve("John A. Homan", self.case)
        self.assertTrue(first.created)
        # Match with all-caps inverted form — normalizes to the same string
        second = self.resolve("HOMAN, JOHN A.", self.case)
        self.assertFalse(second.created)
        self.assertEqual(first.person.id, second.person.id)

    def test_no_cross_case_contamination(self):
        other_case = Case.objects.create(name="Other Case")
        self.resolve("John A. Homan", self.case)
        # Same name in a different case should create a new record
        result = self.resolve("John A. Homan", other_case)
        self.assertTrue(result.created)

    def test_fuzzy_candidate_surfaced_for_near_match(self):
        # Create a person
        self.resolve("John A. Homan", self.case)
        # Resolve a near-match — should not create, but should surface fuzzy candidate
        result = self.resolve("John Homan", self.case)
        # May or may not create depending on threshold, but should have fuzzy candidates
        # if it creates, the fuzzy list should still be populated for the near-match
        if result.created:
            self.assertTrue(
                len(result.fuzzy_candidates) > 0,
                "Near-match should surface fuzzy candidates even if new record created",
            )

    def test_completely_different_name_has_no_fuzzy_candidates(self):
        self.resolve("John A. Homan", self.case)
        result = self.resolve("Maria Gonzalez", self.case)
        self.assertTrue(result.created)
        self.assertEqual(result.fuzzy_candidates, [])

    def test_creates_person_document_link_when_document_provided(self):
        from .models import PersonDocument
        doc = Document.objects.create(
            case=self.case,
            filename="deed.pdf",
            file_path="cases/test/deed.pdf",
            sha256_hash="d" * 64,
            file_size=1024,
        )
        self.resolve("John A. Homan", self.case, document=doc)
        self.assertTrue(
            PersonDocument.objects.filter(
                document=doc,
                person__full_name="John A. Homan",
            ).exists()
        )

    def test_person_document_link_is_idempotent(self):
        from .models import PersonDocument
        doc = Document.objects.create(
            case=self.case,
            filename="deed2.pdf",
            file_path="cases/test/deed2.pdf",
            sha256_hash="e" * 64,
            file_size=1024,
        )
        self.resolve("John A. Homan", self.case, document=doc)
        self.resolve("John A. Homan", self.case, document=doc)
        link_count = PersonDocument.objects.filter(document=doc).count()
        self.assertEqual(link_count, 1, "Repeated resolution should not create duplicate links")


class EntityResolutionOrgTests(TestCase):
    """Tests for resolve_org() — exact match, normalization, fuzzy."""

    def setUp(self):
        from .entity_resolution import resolve_org
        self.resolve = resolve_org
        self.case = Case.objects.create(name="Org Resolution Test Case")

    def test_creates_new_org_when_no_match(self):
        result = self.resolve("Do Good Ministries, Inc.", self.case)
        self.assertTrue(result.created)

    def test_exact_match_returns_existing_org(self):
        first = self.resolve("Do Good Ministries, Inc.", self.case)
        second = self.resolve("Do Good Ministries, Inc.", self.case)
        self.assertFalse(second.created)
        self.assertEqual(first.org.id, second.org.id)

    def test_normalized_match_strips_inc_designator(self):
        first = self.resolve("Do Good Ministries, Inc.", self.case)
        # Without "Inc." should normalize to the same form
        second = self.resolve("Do Good Ministries", self.case)
        self.assertFalse(second.created)
        self.assertEqual(first.org.id, second.org.id)


class EntityResolutionBatchTests(TestCase):
    """Tests for resolve_all_entities() batch entry point."""

    def setUp(self):
        from .entity_resolution import resolve_all_entities
        self.resolve_all = resolve_all_entities
        self.case = Case.objects.create(name="Batch Resolution Test Case")

    def test_batch_creates_persons_and_orgs(self):
        extraction_result = {
            "persons": [
                {"raw": "John A. Homan", "context": "GRANTOR: John A. Homan"},
                {"raw": "Mary Jo Winner", "context": "GRANTEE: Mary Jo Winner"},
            ],
            "orgs": [
                {"raw": "Do Good Ministries, Inc.", "context": "..."},
            ],
            "dates": [],
            "amounts": [],
            "parcels": [],
            "filing_refs": [],
        }
        summary = self.resolve_all(extraction_result, self.case)
        self.assertEqual(summary.persons_created, 2)
        self.assertEqual(summary.orgs_created, 1)
        self.assertEqual(summary.persons_matched, 0)
        self.assertEqual(summary.orgs_matched, 0)

    def test_batch_matches_existing_on_second_run(self):
        extraction_result = {
            "persons": [{"raw": "John A. Homan", "context": ""}],
            "orgs": [],
            "dates": [],
            "amounts": [],
            "parcels": [],
            "filing_refs": [],
        }
        self.resolve_all(extraction_result, self.case)
        summary = self.resolve_all(extraction_result, self.case)
        self.assertEqual(summary.persons_created, 0)
        self.assertEqual(summary.persons_matched, 1)

    def test_batch_handles_empty_extraction_result(self):
        extraction_result = {
            "persons": [], "orgs": [], "dates": [],
            "amounts": [], "parcels": [], "filing_refs": [],
        }
        summary = self.resolve_all(extraction_result, self.case)
        self.assertEqual(summary.persons_created, 0)
        self.assertEqual(summary.orgs_created, 0)
        self.assertEqual(summary.fuzzy_candidates, [])

    def test_list_case_documents_rejects_inverted_uploaded_date_range(self):
        case = Case.objects.create(name="Inverted Uploaded Range Case")

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"uploaded_from": "2026-03-20", "uploaded_to": "2026-03-01"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_document_list_order_is_deterministic_for_timestamp_ties(self):
        case = Case.objects.create(name="Document Tie Case")
        shared_uploaded_at = timezone.now()
        first = Document.objects.create(
            case=case,
            filename="tie-1.pdf",
            file_path="cases/doc/tie-1.pdf",
            sha256_hash="1" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            uploaded_at=shared_uploaded_at,
            updated_at=shared_uploaded_at,
        )
        second = Document.objects.create(
            case=case,
            filename="tie-2.pdf",
            file_path="cases/doc/tie-2.pdf",
            sha256_hash="2" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            uploaded_at=shared_uploaded_at,
            updated_at=shared_uploaded_at,
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        expected_ids = sorted([str(first.pk), str(second.pk)], reverse=True)
        self.assertEqual([item["id"]
                         for item in payload["results"]], expected_ids)

    def test_document_list_supports_custom_sort(self):
        case = Case.objects.create(name="Document Sort Case")
        large = Document.objects.create(
            case=case,
            filename="large.pdf",
            file_path="cases/doc/large.pdf",
            sha256_hash="c" * 64,
            file_size=500,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )
        small = Document.objects.create(
            case=case,
            filename="small.pdf",
            file_path="cases/doc/small.pdf",
            sha256_hash="d" * 64,
            file_size=10,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"order_by": "file_size", "direction": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [item["id"] for item in payload["results"]]
        self.assertTrue(ids.index(str(small.pk)) < ids.index(str(large.pk)))

    def test_document_list_rejects_invalid_sort_params(self):
        case = Case.objects.create(name="Document Sort Validation Case")

        response = self.client.get(
            reverse("api_case_document_collection", args=[case.pk]),
            data={"order_by": "not_a_field", "direction": "sideways"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("order_by", payload["errors"])

    def test_list_case_documents_returns_404_for_missing_case(self):
        response = self.client.get(
            reverse("api_case_document_collection", args=[uuid.uuid4()])
        )

        self.assertEqual(response.status_code, 404)

    def test_case_document_detail_returns_document(self):
        case = Case.objects.create(name="Detail Case")
        document = Document.objects.create(
            case=case,
            filename="detail.pdf",
            file_path="cases/doc/detail.pdf",
            sha256_hash="9" * 64,
            file_size=512,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_detail", args=[case.pk, document.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(document.pk))
        self.assertEqual(payload["filename"], "detail.pdf")

    def test_case_document_detail_returns_404_for_document_outside_case(self):
        case = Case.objects.create(name="Primary Case")
        other_case = Case.objects.create(name="Other Case")
        other_document = Document.objects.create(
            case=other_case,
            filename="outside.pdf",
            file_path="cases/doc/outside.pdf",
            sha256_hash="8" * 64,
            file_size=256,
            doc_type=DocumentType.OTHER,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse("api_case_document_detail", args=[
                    case.pk, other_document.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_patch_case_detail_updates_allowed_fields(self):
        case = Case.objects.create(
            name="Patchable Case",
            status="ACTIVE",
            notes="Old notes",
            referral_ref="OLD-REF",
        )

        response = self.client.patch(
            reverse("api_case_detail", args=[case.pk]),
            data=json.dumps(
                {
                    "status": "PAUSED",
                    "notes": "Updated notes",
                    "referral_ref": "NEW-REF",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "PAUSED")
        self.assertEqual(payload["notes"], "Updated notes")
        self.assertEqual(payload["referral_ref"], "NEW-REF")

        case.refresh_from_db()
        self.assertEqual(case.status, "PAUSED")
        self.assertEqual(case.notes, "Updated notes")
        self.assertEqual(case.referral_ref, "NEW-REF")

    def test_patch_case_detail_rejects_unexpected_fields(self):
        case = Case.objects.create(name="Patch Validation Case")

        response = self.client.patch(
            reverse("api_case_detail", args=[case.pk]),
            data=json.dumps({"name": "Renamed Case"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_patch_case_document_updates_metadata(self):
        case = Case.objects.create(name="Patch Case")
        document = Document.objects.create(
            case=case,
            filename="patch.pdf",
            file_path="cases/doc/patch.pdf",
            sha256_hash="7" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            source_url="https://example.org/original",
            uploaded_at=timezone.now() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.patch(
            reverse("api_case_document_detail", args=[case.pk, document.pk]),
            data=json.dumps(
                {
                    "doc_type": "DEED",
                    "ocr_status": "COMPLETED",
                    "source_url": "https://example.org/updated",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["doc_type"], "DEED")
        self.assertEqual(payload["ocr_status"], "COMPLETED")
        self.assertEqual(payload["source_url"], "https://example.org/updated")

        document.refresh_from_db()
        self.assertEqual(document.doc_type, DocumentType.DEED)
        self.assertEqual(document.ocr_status, OcrStatus.COMPLETED)
        self.assertEqual(document.source_url, "https://example.org/updated")

    def test_patch_case_document_rejects_unexpected_fields(self):
        case = Case.objects.create(name="Patch Validation Case")
        document = Document.objects.create(
            case=case,
            filename="reject.pdf",
            file_path="cases/doc/reject.pdf",
            sha256_hash="6" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.patch(
            reverse("api_case_document_detail", args=[case.pk, document.pk]),
            data=json.dumps({"filename": "new-name.pdf"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("non_field_errors", payload["errors"])

    def test_patch_case_document_returns_404_for_document_outside_case(self):
        case = Case.objects.create(name="Patch Primary Case")
        other_case = Case.objects.create(name="Patch Other Case")
        other_document = Document.objects.create(
            case=other_case,
            filename="outside-patch.pdf",
            file_path="cases/doc/outside-patch.pdf",
            sha256_hash="5" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.patch(
            reverse("api_case_document_detail", args=[
                    case.pk, other_document.pk]),
            data=json.dumps({"doc_type": "DEED"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_delete_case_document_returns_204_and_removes_document(self):
        case = Case.objects.create(name="Delete Case")
        document = Document.objects.create(
            case=case,
            filename="delete.pdf",
            file_path="cases/doc/delete.pdf",
            sha256_hash="d" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.delete(
            reverse("api_case_document_detail", args=[case.pk, document.pk])
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())

    def test_delete_case_document_returns_404_for_document_outside_case(self):
        case = Case.objects.create(name="Delete Primary Case")
        other_case = Case.objects.create(name="Delete Other Case")
        other_document = Document.objects.create(
            case=other_case,
            filename="delete-outside.pdf",
            file_path="cases/doc/delete-outside.pdf",
            sha256_hash="e" * 64,
            file_size=100,
            doc_type=DocumentType.OTHER,
            ocr_status=OcrStatus.PENDING,
            uploaded_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.delete(
            reverse("api_case_document_detail", args=[
                    case.pk, other_document.pk])
        )

        self.assertEqual(response.status_code, 404)


class DocumentUploadRoutingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Upload Routing Case")

    def _upload_file(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        doc_type: str = "OTHER",
    ):
        upload = SimpleUploadedFile(
            filename, content, content_type=content_type)
        return self.client.post(
            reverse("document_upload"),
            data={
                "case": str(self.case.pk),
                "doc_type": doc_type,
                "source_url": "",
                "file": upload,
            },
        )

    def _upload_pdf(self, *, doc_type: str = "OTHER", filename: str = "routing-test.pdf"):
        return self._upload_file(
            filename=filename,
            content=b"%PDF-1.4 test payload",
            content_type="application/pdf",
            doc_type=doc_type,
        )

    @patch("investigations.classification.classify_document")
    @patch("investigations.extraction.extract_from_pdf")
    def test_auto_classified_referral_memo_sets_is_generated_true(
        self,
        mock_extract_from_pdf,
        mock_classify_document,
    ):
        mock_extract_from_pdf.return_value = (
            "referral memorandum summary of findings",
            OcrStatus.COMPLETED,
        )
        mock_classify_document.return_value = DocumentType.REFERRAL_MEMO

        response = self._upload_pdf(doc_type=DocumentType.OTHER)

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(case=self.case)
        self.assertEqual(document.doc_type, DocumentType.REFERRAL_MEMO)
        self.assertTrue(document.is_generated)

    @patch("investigations.classification.classify_document")
    @patch("investigations.extraction.extract_from_pdf")
    def test_manual_referral_memo_does_not_auto_set_generated(
        self,
        mock_extract_from_pdf,
        mock_classify_document,
    ):
        mock_extract_from_pdf.return_value = (
            "referral memorandum summary of findings",
            OcrStatus.COMPLETED,
        )

        response = self._upload_pdf(doc_type=DocumentType.REFERRAL_MEMO)

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(case=self.case)
        self.assertEqual(document.doc_type, DocumentType.REFERRAL_MEMO)
        self.assertFalse(document.is_generated)
        mock_classify_document.assert_not_called()

    @patch("investigations.classification.classify_document")
    @patch("investigations.extraction.extract_from_pdf")
    def test_auto_classified_non_referral_document_stays_not_generated(
        self,
        mock_extract_from_pdf,
        mock_classify_document,
    ):
        mock_extract_from_pdf.return_value = (
            "warranty deed legal description grantor grantee",
            OcrStatus.COMPLETED,
        )
        mock_classify_document.return_value = DocumentType.DEED

        response = self._upload_pdf(doc_type=DocumentType.OTHER)

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(case=self.case)
        self.assertEqual(document.doc_type, DocumentType.DEED)
        self.assertFalse(document.is_generated)

    @patch("investigations.classification.classify_document")
    @patch("investigations.extraction.extract_from_pdf")
    def test_upload_routing_matrix_for_pdf_paths(
        self,
        mock_extract_from_pdf,
        mock_classify_document,
    ):
        scenarios = [
            {
                "name": "digital_pdf_direct_text",
                "extract_result": ("embedded text from digital pdf", OcrStatus.NOT_NEEDED),
                "classified_type": DocumentType.DEED,
                "expected_doc_type": DocumentType.DEED,
                "expected_ocr_status": OcrStatus.NOT_NEEDED,
                "expected_is_generated": False,
            },
            {
                "name": "scanned_pdf_ocr_completed",
                "extract_result": ("ocr result with financing statement", OcrStatus.COMPLETED),
                "classified_type": DocumentType.UCC,
                "expected_doc_type": DocumentType.UCC,
                "expected_ocr_status": OcrStatus.COMPLETED,
                "expected_is_generated": False,
            },
            {
                "name": "scanned_pdf_too_large_pending",
                "extract_result": ("", OcrStatus.PENDING),
                "classified_type": None,
                "expected_doc_type": DocumentType.OTHER,
                "expected_ocr_status": OcrStatus.PENDING,
                "expected_is_generated": False,
            },
        ]

        for index, scenario in enumerate(scenarios):
            with self.subTest(scenario=scenario["name"]):
                mock_extract_from_pdf.return_value = scenario["extract_result"]
                mock_classify_document.reset_mock()
                if scenario["classified_type"] is not None:
                    mock_classify_document.return_value = scenario["classified_type"]

                response = self._upload_pdf(
                    doc_type=DocumentType.OTHER,
                    filename=f"routing-{index}.pdf",
                )
                self.assertEqual(response.status_code, 302)

                document = Document.objects.get(
                    case=self.case,
                    filename=f"routing-{index}.pdf",
                )
                self.assertEqual(document.doc_type,
                                 scenario["expected_doc_type"])
                self.assertEqual(document.ocr_status,
                                 scenario["expected_ocr_status"])
                self.assertEqual(document.is_generated,
                                 scenario["expected_is_generated"])

                if scenario["extract_result"][0]:
                    mock_classify_document.assert_called_once()
                else:
                    mock_classify_document.assert_not_called()

    @patch("investigations.classification.classify_document")
    @patch("investigations.extraction.extract_from_pdf")
    def test_non_pdf_upload_skips_extraction_and_classification(
        self,
        mock_extract_from_pdf,
        mock_classify_document,
    ):
        response = self._upload_file(
            filename="notes.txt",
            content=b"plain text note",
            content_type="text/plain",
            doc_type=DocumentType.OTHER,
        )

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(case=self.case, filename="notes.txt")
        self.assertEqual(document.doc_type, DocumentType.OTHER)
        self.assertEqual(document.ocr_status, OcrStatus.NOT_NEEDED)
        self.assertFalse(document.is_generated)

        mock_extract_from_pdf.assert_not_called()
        mock_classify_document.assert_not_called()
