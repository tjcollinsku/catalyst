"""Tests for the 4 new Phase D endpoints:
- GET  /api/search/
- GET  /api/cases/<uuid>/export/
- GET  /api/entities/<type>/<uuid>/
- GET/POST /api/cases/<uuid>/notes/
- GET/PATCH/DELETE /api/cases/<uuid>/notes/<uuid>/
"""

import json
import uuid

from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Case,
    Document,
    DocumentType,
    EntitySignal,
    FinancialInstrument,
    InvestigatorNote,
    OcrStatus,
    Organization,
    Person,
    PersonDocument,
    Property,
    Signal,
)


class SearchApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Smith Fraud Investigation")

    def test_search_requires_minimum_query_length(self):
        response = self.client.get(reverse("api_search"), data={"q": "a"})
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("q", payload["errors"])

    def test_search_finds_cases_by_name(self):
        response = self.client.get(reverse("api_search"), data={"q": "Smith"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "Smith")
        self.assertGreaterEqual(payload["total"], 1)
        types = [r["type"] for r in payload["results"]]
        self.assertIn("case", types)

    def test_search_finds_documents_by_filename(self):
        Document.objects.create(
            case=self.case,
            filename="smith_deed_transfer.pdf",
            file_path="cases/doc/smith.pdf",
            sha256_hash="a" * 64,
            file_size=1024,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.COMPLETED,
        )
        response = self.client.get(reverse("api_search"), data={"q": "smith_deed"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        doc_results = [r for r in payload["results"] if r["type"] == "document"]
        self.assertGreaterEqual(len(doc_results), 1)

    def test_search_finds_documents_by_extracted_text(self):
        Document.objects.create(
            case=self.case,
            filename="doc.pdf",
            file_path="cases/doc/doc.pdf",
            sha256_hash="b" * 64,
            file_size=1024,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.COMPLETED,
            extracted_text="This deed transfers property from John Doe to Jane Smith.",
        )
        response = self.client.get(reverse("api_search"), data={"q": "John Doe"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        doc_results = [r for r in payload["results"] if r["type"] == "document"]
        self.assertGreaterEqual(len(doc_results), 1)

    def test_search_finds_persons(self):
        Person.objects.create(case=self.case, full_name="Robert Smith")
        response = self.client.get(reverse("api_search"), data={"q": "Robert"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        entity_results = [r for r in payload["results"] if r["type"] == "entity"]
        self.assertGreaterEqual(len(entity_results), 1)

    def test_search_filters_by_type(self):
        Person.objects.create(case=self.case, full_name="Smith Person")
        response = self.client.get(reverse("api_search"), data={"q": "Smith", "type": "entity"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        types = set(r["type"] for r in payload["results"])
        self.assertEqual(types, {"entity"})

    def test_search_filters_by_case_id(self):
        _other_case = Case.objects.create(name="Smith Other Case")
        response = self.client.get(
            reverse("api_search"),
            data={"q": "Smith", "case_id": str(self.case.pk)},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for r in payload["results"]:
            self.assertEqual(r["case_id"], str(self.case.pk))

    def test_search_rejects_invalid_type(self):
        response = self.client.get(reverse("api_search"), data={"q": "test", "type": "badtype"})
        self.assertEqual(response.status_code, 400)

    def test_search_returns_empty_for_no_matches(self):
        response = self.client.get(reverse("api_search"), data={"q": "zzzznonexistent"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["results"], [])


class CaseExportApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Export Test Case", status="ACTIVE")
        Document.objects.create(
            case=self.case,
            filename="evidence.pdf",
            file_path="cases/doc/evidence.pdf",
            sha256_hash="a" * 64,
            file_size=2048,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.COMPLETED,
        )
        Person.objects.create(case=self.case, full_name="John Doe")

    def test_json_export_returns_metadata(self):
        response = self.client.get(
            reverse("api_case_export", args=[self.case.pk]),
            data={"format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "json")
        self.assertIn("filename", payload)
        self.assertIn("download_url", payload)
        self.assertIn(".json", payload["filename"])

    def test_csv_export_returns_metadata(self):
        response = self.client.get(
            reverse("api_case_export", args=[self.case.pk]),
            data={"format": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "csv")
        self.assertIn("filename", payload)
        self.assertIn("download_url", payload)
        self.assertIn(".csv", payload["filename"])

    def test_export_defaults_to_json(self):
        response = self.client.get(reverse("api_case_export", args=[self.case.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "json")

    def test_export_rejects_invalid_format(self):
        response = self.client.get(
            reverse("api_case_export", args=[self.case.pk]),
            data={"format": "xml"},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("format", payload["errors"])

    def test_export_returns_404_for_missing_case(self):
        response = self.client.get(reverse("api_case_export", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)


class EntityDetailApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Entity Detail Case")

    def test_person_detail_returns_full_data(self):
        person = Person.objects.create(
            case=self.case,
            full_name="Jane Smith",
            role_tags=["OFFICER", "BOARD_MEMBER"],
        )
        response = self.client.get(reverse("api_entity_detail", args=["person", person.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Jane Smith")
        self.assertEqual(payload["entity_type"], "person")
        self.assertIn("related_documents", payload)
        self.assertIn("related_signals", payload)
        self.assertIn("related_findings", payload)
        self.assertIn("organization_roles", payload)

    def test_organization_detail_returns_full_data(self):
        org = Organization.objects.create(case=self.case, name="Acme LLC", org_type="LLC")
        response = self.client.get(reverse("api_entity_detail", args=["organization", org.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Acme LLC")
        self.assertEqual(payload["entity_type"], "organization")

    def test_property_detail_includes_transactions(self):
        prop = Property.objects.create(case=self.case, address="123 Main St", county="Franklin")
        response = self.client.get(reverse("api_entity_detail", args=["property", prop.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entity_type"], "property")
        self.assertIn("transactions", payload)

    def test_financial_instrument_detail(self):
        fi = FinancialInstrument.objects.create(
            case=self.case,
            instrument_type="UCC_FILING",
            filing_number="UCC-12345",
        )
        response = self.client.get(
            reverse("api_entity_detail", args=["financial_instrument", fi.pk])
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entity_type"], "financial_instrument")

    def test_person_detail_includes_related_documents(self):
        person = Person.objects.create(case=self.case, full_name="Test Person")
        doc = Document.objects.create(
            case=self.case,
            filename="person_doc.pdf",
            file_path="cases/doc/person_doc.pdf",
            sha256_hash="d" * 64,
            file_size=512,
            doc_type=DocumentType.DEED,
            ocr_status=OcrStatus.COMPLETED,
        )
        PersonDocument.objects.create(
            person=person,
            document=doc,
            page_reference="p.3",
            context_note="Named as grantor",
        )
        response = self.client.get(reverse("api_entity_detail", args=["person", person.pk]))
        payload = response.json()
        self.assertEqual(len(payload["related_documents"]), 1)
        self.assertEqual(payload["related_documents"][0]["filename"], "person_doc.pdf")
        self.assertEqual(payload["related_documents"][0]["page_reference"], "p.3")

    def test_person_detail_includes_related_signals(self):
        person = Person.objects.create(case=self.case, full_name="Signaled Person")
        signal = Signal.objects.create(
            case=self.case,
            rule_id="SR-001",
            severity="CRITICAL",
            detected_summary="Deceased person found",
        )
        EntitySignal.objects.create(signal=signal, entity_id=person.pk, entity_type="person")
        response = self.client.get(reverse("api_entity_detail", args=["person", person.pk]))
        payload = response.json()
        self.assertEqual(len(payload["related_signals"]), 1)

    def test_entity_detail_rejects_invalid_type(self):
        response = self.client.get(reverse("api_entity_detail", args=["badtype", uuid.uuid4()]))
        self.assertEqual(response.status_code, 400)

    def test_entity_detail_returns_404_for_missing_entity(self):
        response = self.client.get(reverse("api_entity_detail", args=["person", uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)


class InvestigatorNoteApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Notes Test Case")

    def test_create_note(self):
        response = self.client.post(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data=json.dumps(
                {
                    "target_type": "case",
                    "target_id": str(self.case.pk),
                    "content": "Initial investigation note.",
                    "created_by": "Investigator Adams",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["content"], "Initial investigation note.")
        self.assertEqual(payload["created_by"], "Investigator Adams")
        self.assertEqual(InvestigatorNote.objects.count(), 1)

    def test_create_note_rejects_empty_content(self):
        response = self.client.post(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data=json.dumps(
                {
                    "target_type": "case",
                    "target_id": str(self.case.pk),
                    "content": "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("content", payload["errors"])

    def test_create_note_rejects_invalid_target_type(self):
        response = self.client.post(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data=json.dumps(
                {
                    "target_type": "invalidtype",
                    "target_id": str(self.case.pk),
                    "content": "Some note.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("target_type", payload["errors"])

    def test_create_note_rejects_invalid_target_id(self):
        response = self.client.post(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data=json.dumps(
                {
                    "target_type": "case",
                    "target_id": "not-a-uuid",
                    "content": "Some note.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("target_id", payload["errors"])

    def test_list_notes_with_pagination(self):
        for i in range(3):
            InvestigatorNote.objects.create(
                case=self.case,
                target_type="case",
                target_id=self.case.pk,
                content=f"Note {i}",
            )
        response = self.client.get(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data={"limit": "2", "offset": "0"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(payload["next_offset"], 2)

    def test_list_notes_filters_by_target_type(self):
        InvestigatorNote.objects.create(
            case=self.case,
            target_type="case",
            target_id=self.case.pk,
            content="Case note",
        )
        InvestigatorNote.objects.create(
            case=self.case,
            target_type="document",
            target_id=uuid.uuid4(),
            content="Document note",
        )
        response = self.client.get(
            reverse("api_case_note_collection", args=[self.case.pk]),
            data={"target_type": "case"},
        )
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["content"], "Case note")

    def test_get_note_detail(self):
        note = InvestigatorNote.objects.create(
            case=self.case,
            target_type="case",
            target_id=self.case.pk,
            content="Detail note.",
        )
        response = self.client.get(reverse("api_case_note_detail", args=[self.case.pk, note.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["content"], "Detail note.")

    def test_update_note(self):
        note = InvestigatorNote.objects.create(
            case=self.case,
            target_type="case",
            target_id=self.case.pk,
            content="Original content.",
        )
        response = self.client.patch(
            reverse("api_case_note_detail", args=[self.case.pk, note.pk]),
            data=json.dumps({"content": "Updated content."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["content"], "Updated content.")

    def test_update_note_rejects_empty_content(self):
        note = InvestigatorNote.objects.create(
            case=self.case,
            target_type="case",
            target_id=self.case.pk,
            content="Valid content.",
        )
        response = self.client.patch(
            reverse("api_case_note_detail", args=[self.case.pk, note.pk]),
            data=json.dumps({"content": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_note(self):
        note = InvestigatorNote.objects.create(
            case=self.case,
            target_type="case",
            target_id=self.case.pk,
            content="Deletable note.",
        )
        response = self.client.delete(reverse("api_case_note_detail", args=[self.case.pk, note.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(InvestigatorNote.objects.filter(pk=note.pk).exists())

    def test_note_detail_returns_404_for_wrong_case(self):
        other_case = Case.objects.create(name="Other Case")
        note = InvestigatorNote.objects.create(
            case=other_case,
            target_type="case",
            target_id=other_case.pk,
            content="Wrong case note.",
        )
        response = self.client.get(reverse("api_case_note_detail", args=[self.case.pk, note.pk]))
        self.assertEqual(response.status_code, 404)

    def test_note_collection_returns_404_for_missing_case(self):
        response = self.client.get(reverse("api_case_note_collection", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)


class ResearchAddToCaseTests(TestCase):
    """Tests for the POST /api/cases/<uuid>/research/add-to-case/ endpoint."""

    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="Research Integration Case")

    def test_add_property_from_parcel_search(self):
        """Test creating a Property entity from parcel search result."""
        payload = {
            "source": "parcels",
            "data": {
                "pin": "123-456-789",
                "owner1": "John Doe",
                "county": "Darke",
                "acres_calc": 15.5,
                "aud_link": "https://auditor.example.com/parcel",
            },
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], "property")
        self.assertFalse(data["duplicate"])
        self.assertIn("entity", data)
        self.assertEqual(data["entity"]["parcel_number"], "123-456-789")

        # Verify property was created
        prop = Property.objects.get(case=self.case, parcel_number="123-456-789")
        self.assertEqual(prop.current_owner_name, "John Doe")
        self.assertEqual(prop.county, "Darke")
        self.assertEqual(float(prop.acreage), 15.5)

    def test_duplicate_property_detection(self):
        """Test that duplicate properties return existing entity."""
        Property.objects.create(
            case=self.case,
            parcel_number="123-456-789",
            county="Darke",
            current_owner_name="John Doe",
        )

        payload = {
            "source": "parcels",
            "data": {
                "pin": "123-456-789",
                "owner1": "John Doe",
                "county": "Darke",
                "acres_calc": 15.5,
                "aud_link": "https://auditor.example.com/parcel",
            },
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], "property")
        self.assertTrue(data["duplicate"])

    def test_add_organization_from_ohio_sos(self):
        """Test creating an Organization entity from Ohio SOS result."""
        payload = {
            "source": "ohio-sos",
            "data": {
                "business_name": "Goodwill Nonprofit LLC",
                "entity_number": "OH123456",
                "status": "ACTIVE",
                "filing_date": "2020-01-15",
                "county": "Franklin",
            },
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], "organization")
        self.assertFalse(data["duplicate"])
        self.assertEqual(data["entity"]["name"], "Goodwill Nonprofit LLC")

        # Verify organization was created
        org = Organization.objects.get(case=self.case, name="Goodwill Nonprofit LLC")
        self.assertEqual(org.status, "ACTIVE")

    def test_add_investigator_note_from_ohio_aos(self):
        """Test creating an InvestigatorNote from Ohio AOS audit result."""
        payload = {
            "source": "ohio-aos",
            "data": {
                "entity_name": "Smith Foundation",
                "county": "Franklin",
                "report_type": "Financial Audit",
                "period": "2022-2023",
                "has_findings_for_recovery": True,
                "pdf_url": "https://aos.example.com/reports/smith.pdf",
            },
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], "note")
        self.assertFalse(data["duplicate"])

        # Verify note was created
        note = InvestigatorNote.objects.get(case=self.case)
        self.assertIn("Smith Foundation", note.content)
        self.assertIn("Findings for Recovery: YES", note.content)

    def test_add_organization_from_irs(self):
        """Test creating an Organization entity from IRS search result."""
        payload = {
            "source": "irs",
            "data": {
                "organization_name": "Community Care Foundation",
                "ein": "45-1234567",
                "state": "OH",
                "ruling_date": "2010-06-15",
                "deductibility_code": "501(c)(3)",
                "total_revenue": 500000,
                "total_assets": 2000000,
            },
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], "organization")
        self.assertFalse(data["duplicate"])
        self.assertEqual(data["entity"]["ein"], "45-1234567")

        # Verify organization was created
        org = Organization.objects.get(case=self.case, ein="45-1234567")
        self.assertEqual(org.org_type, "CHARITY")

    def test_recorder_source_returns_error(self):
        """Test that recorder source returns appropriate error."""
        payload = {
            "source": "recorder",
            "data": {},
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Recorder results are portal links", data["error"])

    def test_missing_source_returns_error(self):
        """Test that missing source field returns 400."""
        payload = {
            "data": {"some": "data"},
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("source", data["error"])

    def test_invalid_json_returns_error(self):
        """Test that invalid JSON returns 400."""
        response = self.client.post(
            reverse("api_research_add_to_case", args=[self.case.pk]),
            "invalid json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_case_returns_404(self):
        """Test that missing case returns 404."""
        payload = {
            "source": "parcels",
            "data": {"pin": "123-456"},
        }
        response = self.client.post(
            reverse("api_research_add_to_case", args=[uuid.uuid4()]),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
