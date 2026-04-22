"""Tests for ai_pattern_augmentation: context builder, parsing, end-to-end."""

import json
from unittest.mock import patch

from django.test import TestCase

from investigations import ai_pattern_augmentation
from investigations.models import (
    Case,
    Document,
    FinancialSnapshot,
    Finding,
    FindingSource,
    Organization,
    Person,
)


class BuildContextTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="Test Case", status="ACTIVE")
        self.person = Person.objects.create(
            case=self.case,
            full_name="Karen Example",
        )
        self.org = Organization.objects.create(
            case=self.case,
            name="Example Foundation",
            ein="12-3456789",
        )
        self.doc = Document.objects.create(
            case=self.case,
            filename="2021_990.pdf",
            file_path="/tmp/2021_990.pdf",
            sha256_hash="a" * 64,
            file_size=1000,
            doc_type="FORM_990",
            extracted_text="Part VII lists Karen Example as president..." * 100,
        )
        FinancialSnapshot.objects.create(
            document=self.doc,
            case=self.case,
            organization=self.org,
            tax_year=2021,
            total_revenue=500000,
            total_expenses=400000,
            net_assets_eoy=100000,
        )

    def test_includes_case_and_entities(self):
        ctx = ai_pattern_augmentation.build_context(self.case)
        self.assertEqual(ctx["case"]["name"], "Test Case")
        self.assertTrue(any(p["name"] == "Karen Example" for p in ctx["entities"]["persons"]))
        self.assertTrue(any(o["ein"] == "12-3456789" for o in ctx["entities"]["organizations"]))

    def test_includes_financials(self):
        ctx = ai_pattern_augmentation.build_context(self.case)
        self.assertTrue(
            any(f["tax_year"] == 2021 and f["revenue"] == 500000 for f in ctx["financial_snapshots"])
        )

    def test_assigns_doc_refs(self):
        ctx = ai_pattern_augmentation.build_context(self.case)
        docs = ctx["documents"]
        self.assertGreaterEqual(len(docs), 1)
        self.assertEqual(docs[0]["ref"], "Doc-1")
        self.assertEqual(docs[0]["filename"], "2021_990.pdf")
        self.assertIn("text_excerpt", docs[0])

    def test_truncates_document_text(self):
        ctx = ai_pattern_augmentation.build_context(self.case)
        for d in ctx["documents"]:
            self.assertLessEqual(len(d["text_excerpt"]), 2000)

    def test_returns_doc_ref_map(self):
        ctx, doc_ref_map = ai_pattern_augmentation.build_context_with_refs(self.case)
        self.assertEqual(len(doc_ref_map), len(ctx["documents"]))
        self.assertTrue(all(ref.startswith("Doc-") for ref in doc_ref_map.keys()))


class ParseResponseTests(TestCase):
    def test_happy_path(self):
        raw = json.dumps({
            "patterns": [
                {
                    "title": "Name variant",
                    "description": "K. S. Example ~ Karen Example",
                    "rationale": "Overlapping city and last name",
                    "evidence_weight": "DIRECTIONAL",
                    "entity_refs": ["uuid-a"],
                    "doc_refs": ["Doc-1", "Doc-2"],
                    "suggested_action": "Pull 2020 990",
                }
            ]
        })
        parsed = ai_pattern_augmentation.parse_response(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["title"], "Name variant")

    def test_malformed_returns_empty(self):
        self.assertEqual(ai_pattern_augmentation.parse_response("not json"), [])
        self.assertEqual(ai_pattern_augmentation.parse_response("{}"), [])
        self.assertEqual(
            ai_pattern_augmentation.parse_response('{"patterns": "not a list"}'), []
        )


class ValidatePatternsTests(TestCase):
    def test_drops_invalid_doc_refs(self):
        patterns = [
            {
                "title": "ok",
                "description": "d",
                "rationale": "r",
                "evidence_weight": "DIRECTIONAL",
                "entity_refs": [],
                "doc_refs": ["Doc-1"],
                "suggested_action": "a",
            },
            {
                "title": "bad",
                "description": "d",
                "rationale": "r",
                "evidence_weight": "DIRECTIONAL",
                "entity_refs": [],
                "doc_refs": ["Doc-99"],
                "suggested_action": "a",
            },
        ]
        doc_ref_map = {"Doc-1": "uuid-real"}
        kept, dropped = ai_pattern_augmentation.validate_patterns(patterns, doc_ref_map)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["title"], "ok")
        self.assertEqual(dropped, 1)

    def test_coerces_weight(self):
        patterns = [
            {
                "title": "ok",
                "description": "d",
                "rationale": "r",
                "evidence_weight": "DOCUMENTED",
                "entity_refs": [],
                "doc_refs": ["Doc-1"],
                "suggested_action": "a",
            }
        ]
        kept, _ = ai_pattern_augmentation.validate_patterns(patterns, {"Doc-1": "x"})
        self.assertEqual(kept[0]["evidence_weight"], "DIRECTIONAL")

    def test_requires_required_fields(self):
        patterns = [{"title": "no-body"}]
        kept, dropped = ai_pattern_augmentation.validate_patterns(patterns, {})
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)


def _mock_ai_response(patterns):
    return json.dumps({"patterns": patterns})


class AnalyzeCaseTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="AI Test Case", status="ACTIVE")
        self.doc_a = Document.objects.create(
            case=self.case,
            filename="a.pdf",
            file_path="/tmp/a.pdf",
            sha256_hash="a" * 64,
            file_size=1000,
            doc_type="FORM_990",
            extracted_text="some text",
        )
        self.doc_b = Document.objects.create(
            case=self.case,
            filename="b.pdf",
            file_path="/tmp/b.pdf",
            sha256_hash="b" * 64,
            file_size=1000,
            doc_type="DEED",
            extracted_text="more text",
        )

    @patch("investigations.ai_pattern_augmentation.call_claude")
    def test_writes_findings(self, mock_call):
        mock_call.return_value = _mock_ai_response([
            {
                "title": "Name variant pattern",
                "description": "Looks like same person",
                "rationale": "Matching context",
                "evidence_weight": "DIRECTIONAL",
                "entity_refs": [],
                "doc_refs": ["Doc-1"],
                "suggested_action": "Pull related deed",
            }
        ])
        result = ai_pattern_augmentation.analyze_case(self.case.id)
        self.assertEqual(result["findings_created"], 1)
        self.assertEqual(result["patterns_dropped"], 0)
        findings = Finding.objects.filter(case=self.case, source=FindingSource.AI)
        self.assertEqual(findings.count(), 1)
        f = findings.first()
        self.assertEqual(f.title, "Name variant pattern")
        self.assertEqual(f.evidence_weight, "DIRECTIONAL")
        self.assertEqual(f.status, "NEW")
        self.assertIn("rationale", f.evidence_snapshot)
        self.assertEqual(f.evidence_snapshot["suggested_action"], "Pull related deed")

    @patch("investigations.ai_pattern_augmentation.call_claude")
    def test_drops_invalid_doc_refs(self, mock_call):
        mock_call.return_value = _mock_ai_response([
            {
                "title": "good",
                "description": "d", "rationale": "r", "evidence_weight": "DIRECTIONAL",
                "entity_refs": [], "doc_refs": ["Doc-1"], "suggested_action": "a",
            },
            {
                "title": "bad",
                "description": "d", "rationale": "r", "evidence_weight": "DIRECTIONAL",
                "entity_refs": [], "doc_refs": ["Doc-99"], "suggested_action": "a",
            },
        ])
        result = ai_pattern_augmentation.analyze_case(self.case.id)
        self.assertEqual(result["findings_created"], 1)
        self.assertEqual(result["patterns_dropped"], 1)

    @patch("investigations.ai_pattern_augmentation.call_claude")
    def test_handles_malformed_ai_response(self, mock_call):
        mock_call.return_value = "not json"
        result = ai_pattern_augmentation.analyze_case(self.case.id)
        self.assertEqual(result["findings_created"], 0)

    @patch("investigations.ai_pattern_augmentation.call_claude")
    def test_links_cited_documents(self, mock_call):
        mock_call.return_value = _mock_ai_response([
            {
                "title": "links",
                "description": "d", "rationale": "r", "evidence_weight": "SPECULATIVE",
                "entity_refs": [], "doc_refs": ["Doc-1", "Doc-2"],
                "suggested_action": "a",
            }
        ])
        ai_pattern_augmentation.analyze_case(self.case.id)
        f = Finding.objects.filter(case=self.case, source=FindingSource.AI).first()
        self.assertIsNotNone(f)
        self.assertEqual(f.document_links.count(), 2)
