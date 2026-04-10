"""
Tests for the Signal Detection Engine.

Covers:
  - Rule registry metadata (RULE_REGISTRY)
  - Each rule evaluator: SR-003, SR-004, SR-005, SR-006, SR-010 (KEPT rules only)
  - persist_signals() deduplication logic
  - serialize_finding() output structure
  - FindingUpdateSerializer validation and save
  - GET /api/cases/<pk>/findings/ (list, filters, pagination, sorting)
  - GET /api/cases/<pk>/findings/<finding_id>/ (detail)
  - PATCH /api/cases/<pk>/findings/<finding_id>/ (confirm, dismiss, escalate)
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Case,
    Document,
    FinancialInstrument,
    Finding,
    FindingSource,
    FindingStatus,
    InstrumentType,
    OcrStatus,
    Organization,
    Person,
    Property,
    Severity,
)
from ..serializers import FindingUpdateSerializer, serialize_finding
from ..signal_rules import (
    RULE_REGISTRY,
    SignalTrigger,
    evaluate_case,
    evaluate_document,
    evaluate_sr003_valuation_anomaly,
    evaluate_sr004_ucc_burst,
    evaluate_sr005_zero_consideration,
    evaluate_sr006_990_schedule_l,
    evaluate_sr010_missing_990,
    persist_signals,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(name="Test Case"):
    return Case.objects.create(name=name)


def _make_document(
    case, *, doc_type="OTHER", extracted_text=None, filename="doc.pdf", doc_subtype=""
):
    return Document.objects.create(
        case=case,
        filename=filename,
        file_path=f"cases/{case.pk}/{filename}",
        sha256_hash="a" * 64,
        file_size=1024,
        doc_type=doc_type,
        ocr_status=OcrStatus.COMPLETED,
        extracted_text=extracted_text,
        doc_subtype=doc_subtype,
    )


def _make_person(case, full_name, *, date_of_death=None):
    return Person.objects.create(
        case=case,
        full_name=full_name,
        date_of_death=date_of_death,
    )


def _make_org(case, name, *, org_type="OTHER", formation_date=None):
    return Organization.objects.create(
        case=case,
        name=name,
        org_type=org_type,
        formation_date=formation_date,
    )


def _make_property(case, *, purchase_price=None, assessed_value=None, parcel_number="123"):
    return Property.objects.create(
        case=case,
        parcel_number=parcel_number,
        purchase_price=purchase_price,
        assessed_value=assessed_value,
    )


def _make_ucc(case, filing_number, filing_date):
    return FinancialInstrument.objects.create(
        case=case,
        instrument_type=InstrumentType.UCC_FILING,
        filing_number=filing_number,
        filing_date=filing_date,
    )


def _make_finding(
    case, rule_id="SR-003", severity=Severity.CRITICAL, status=FindingStatus.NEW
):
    return Finding.objects.create(
        case=case,
        rule_id=rule_id,
        title=f"Test finding {rule_id}",
        severity=severity,
        status=status,
        source=FindingSource.AUTO,
    )


# ---------------------------------------------------------------------------
# Rule Registry
# ---------------------------------------------------------------------------


class RuleRegistryTests(TestCase):
    """Ensure all 14 KEPT SR rules are registered with correct severity values."""

    EXPECTED = {
        "SR-003": "HIGH",
        "SR-004": "HIGH",
        "SR-005": "HIGH",
        "SR-006": "HIGH",
        "SR-010": "MEDIUM",
    }

    def test_all_rules_present(self):
        for rule_id in self.EXPECTED:
            with self.subTest(rule_id=rule_id):
                self.assertIn(rule_id, RULE_REGISTRY)

    def test_rule_severities(self):
        for rule_id, expected_severity in self.EXPECTED.items():
            with self.subTest(rule_id=rule_id):
                self.assertEqual(RULE_REGISTRY[rule_id].severity, expected_severity)

    def test_rules_have_title_and_description(self):
        for rule_id, info in RULE_REGISTRY.items():
            with self.subTest(rule_id=rule_id):
                self.assertTrue(info.title, f"{rule_id} has empty title")
                self.assertTrue(info.description, f"{rule_id} has empty description")


# ---------------------------------------------------------------------------
# SR-003 — Valuation Anomaly
# ---------------------------------------------------------------------------


class SR003ValuationAnomalyTests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def test_fires_when_purchase_price_exceeds_assessed_by_over_50pct(self):
        _make_property(
            self.case, purchase_price=Decimal("200000"), assessed_value=Decimal("100000")
        )

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-003")
        self.assertEqual(result[0].severity, "HIGH")  # from RULE_REGISTRY

    def test_fires_when_purchase_price_below_assessed_by_over_50pct(self):
        _make_property(self.case, purchase_price=Decimal("40000"), assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(len(result), 1)
        self.assertIn("below", result[0].detected_summary)

    def test_no_fire_when_deviation_exactly_50pct(self):
        # Exactly 50% — boundary should NOT fire (rule is >50%)
        _make_property(
            self.case, purchase_price=Decimal("150000"), assessed_value=Decimal("100000")
        )

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_deviation_below_50pct(self):
        _make_property(
            self.case, purchase_price=Decimal("120000"), assessed_value=Decimal("100000")
        )

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_assessed_value_is_zero(self):
        _make_property(self.case, purchase_price=Decimal("100000"), assessed_value=Decimal("0"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_purchase_price_missing(self):
        _make_property(self.case, assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_multiple_properties_each_produce_own_signal(self):
        _make_property(
            self.case,
            purchase_price=Decimal("200000"),
            assessed_value=Decimal("100000"),
            parcel_number="P1",
        )
        _make_property(
            self.case,
            purchase_price=Decimal("300000"),
            assessed_value=Decimal("100000"),
            parcel_number="P2",
        )

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# SR-004 — UCC Amendment Burst
# ---------------------------------------------------------------------------


class SR004UccBurstTests(TestCase):
    def setUp(self):
        self.case = _make_case()
        self.base = date(2022, 8, 2)
        # Exactly 16 chars so appended A/B/C fall beyond the [:16] slice,
        # ensuring all three instruments share the same group prefix.
        self.prefix = "OHF-202208020011"

    def _ucc(self, filing_number, offset_days):
        return _make_ucc(self.case, filing_number, self.base + timedelta(days=offset_days))

    def test_fires_when_three_same_prefix_within_24h(self):
        self._ucc(f"{self.prefix}A", 0)
        self._ucc(f"{self.prefix}B", 0)
        self._ucc(f"{self.prefix}C", 1)

        result = evaluate_sr004_ucc_burst(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-004")

    def test_no_fire_when_only_two_within_24h(self):
        self._ucc(f"{self.prefix}A", 0)
        self._ucc(f"{self.prefix}B", 0)

        result = evaluate_sr004_ucc_burst(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_three_spread_over_three_days(self):
        self._ucc(f"{self.prefix}A", 0)
        self._ucc(f"{self.prefix}B", 2)
        self._ucc(f"{self.prefix}C", 4)

        result = evaluate_sr004_ucc_burst(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_fewer_than_three_instruments_total(self):
        self._ucc(f"{self.prefix}A", 0)
        self._ucc(f"{self.prefix}B", 0)

        result = evaluate_sr004_ucc_burst(self.case)

        # Total < 3 threshold for even considering burst
        self.assertEqual(result, [])

    def test_different_prefixes_not_grouped_together(self):
        # Three instruments, but all different master filing numbers
        _make_ucc(self.case, "OHF-00000001A", self.base)
        _make_ucc(self.case, "OHF-00000002B", self.base)
        _make_ucc(self.case, "OHF-00000003C", self.base)

        result = evaluate_sr004_ucc_burst(self.case)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-005 — Zero-Consideration Transfer
# ---------------------------------------------------------------------------


class SR005ZeroConsiderationTests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def test_fires_on_deed_with_zero_dollar_consideration(self):
        doc = _make_document(
            self.case, doc_type="DEED", extracted_text="The consideration for this deed is $0.00."
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-005")

    def test_fires_on_deed_with_love_and_affection_language(self):
        doc = _make_document(
            self.case,
            doc_type="DEED",
            extracted_text="Transferred for love and affection between family members.",
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_fires_on_deed_with_no_consideration_phrase(self):
        doc = _make_document(
            self.case, doc_type="DEED", extracted_text="Transfer made for no consideration."
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_fires_on_recorder_instrument_doc_type(self):
        doc = _make_document(
            self.case,
            doc_type="RECORDER_INSTRUMENT",
            extracted_text="Nominal consideration only — $0.00 paid.",
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_no_fire_on_non_deed_doc_type(self):
        doc = _make_document(
            self.case,
            doc_type="IRS_990",
            extracted_text="No consideration received for this transaction.",
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_normal_consideration_in_deed(self):
        doc = _make_document(
            self.case,
            doc_type="DEED",
            extracted_text="For and in consideration of $250,000.00 paid.",
        )

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_no_text(self):
        doc = _make_document(self.case, doc_type="DEED", extracted_text=None)

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-006 — IRS 990 Schedule L Missing
# ---------------------------------------------------------------------------


class SR006ScheduleLTests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def test_fires_when_28a_yes_without_schedule_l(self):
        text = "Part IV Line 28a Yes — transactions with interested persons occurred."
        doc = _make_document(self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-006")

    def test_no_fire_when_schedule_l_also_present(self):
        text = "Part IV 28a Yes. See Schedule L for detail."
        doc = _make_document(self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_on_non_990_doc_type(self):
        text = "Part IV 28a Yes — this is not a 990."
        doc = _make_document(self.case, doc_type="DEED", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_990_has_no_yes_pattern(self):
        text = "This form 990 does not indicate any interested person transactions."
        doc = _make_document(self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_no_text(self):
        doc = _make_document(self.case, doc_type="IRS_990", extracted_text=None)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-010 — Missing 990
# ---------------------------------------------------------------------------


class SR010Missing990Tests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def test_fires_when_charity_org_and_no_990_docs(self):
        _make_org(self.case, "Example Township Foundation", org_type="CHARITY")

        result = evaluate_sr010_missing_990(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-010")
        self.assertIn("Example Township Foundation", result[0].detected_summary)

    def test_no_fire_when_charity_has_990_doc(self):
        _make_org(self.case, "Example Township Foundation", org_type="CHARITY")
        _make_document(self.case, doc_type="IRS_990", extracted_text="Form 990 filing.")

        result = evaluate_sr010_missing_990(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_no_charity_orgs(self):
        _make_org(self.case, "Some LLC", org_type="LLC")

        result = evaluate_sr010_missing_990(self.case)

        self.assertEqual(result, [])

    def test_one_signal_per_charity_org(self):
        _make_org(self.case, "Charity A", org_type="CHARITY")
        _make_org(self.case, "Charity B", org_type="CHARITY")

        result = evaluate_sr010_missing_990(self.case)

        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# persist_signals() — Deduplication
# ---------------------------------------------------------------------------


class PersistSignalsTests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def _trigger(self, rule_id="SR-010", entity_id=None, doc=None):
        rule = RULE_REGISTRY[rule_id]
        return SignalTrigger(
            rule_id=rule_id,
            severity=rule.severity,
            title=rule.title,
            detected_summary="Test summary.",
            trigger_entity_id=entity_id,
            trigger_doc=doc,
        )

    def test_creates_new_finding(self):
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(len(created), 1)
        self.assertEqual(Finding.objects.count(), 1)

    def test_deduplicates_against_existing_new_finding(self):
        # Pre-create a NEW finding with same rule_id
        Finding.objects.create(
            case=self.case,
            rule_id="SR-010",
            title="Test Finding",
            severity="MEDIUM",
            status=FindingStatus.NEW,
            source=FindingSource.AUTO,
        )
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(created, [])
        self.assertEqual(Finding.objects.count(), 1)  # unchanged

    def test_does_not_deduplicate_against_dismissed_finding(self):
        # DISMISSED findings allow re-fire
        Finding.objects.create(
            case=self.case,
            rule_id="SR-010",
            title="Test Finding",
            severity="MEDIUM",
            status=FindingStatus.DISMISSED,
            source=FindingSource.AUTO,
        )
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(len(created), 1)
        self.assertEqual(Finding.objects.count(), 2)

    def test_persisted_finding_has_correct_fields(self):
        org = _make_org(self.case, "Test Org")
        trigger = SignalTrigger(
            rule_id="SR-010",
            severity="MEDIUM",
            title="Test",
            detected_summary="No 990 found.",
            trigger_entity_id=org.pk,
            trigger_doc=None,
        )
        created = persist_signals(self.case, [trigger])
        finding = created[0]
        self.assertEqual(finding.rule_id, "SR-010")
        self.assertEqual(finding.severity, "MEDIUM")
        self.assertEqual(finding.status, FindingStatus.NEW)
        self.assertEqual(finding.description, "No 990 found.")
        self.assertEqual(finding.source, FindingSource.AUTO)
        self.assertIsNone(finding.trigger_doc_id)

    def test_empty_trigger_list_returns_empty(self):
        created = persist_signals(self.case, [])
        self.assertEqual(created, [])


# ---------------------------------------------------------------------------
# serialize_signal()
# ---------------------------------------------------------------------------


class SerializeFindingTests(TestCase):
    def setUp(self):
        self.case = _make_case()

    def test_serialize_finding_includes_expected_keys(self):
        finding = _make_finding(self.case, rule_id="SR-003")
        data = serialize_finding(finding)
        expected_keys = {
            "id",
            "rule_id",
            "severity",
            "status",
            "title",
            "description",
            "narrative",
            "evidence_weight",
            "source",
            "trigger_entity_id",
            "trigger_doc_id",
            "investigator_note",
            "legal_refs",
            "evidence_snapshot",
            "entity_links",
            "document_links",
            "created_at",
            "updated_at",
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_serialize_finding_title_comes_from_model(self):
        finding = _make_finding(self.case, rule_id="SR-003")
        data = serialize_finding(finding)
        self.assertEqual(data["title"], "Test finding SR-003")

    def test_serialize_finding_unknown_rule_id_uses_rule_id_as_title(self):
        finding = Finding.objects.create(
            case=self.case,
            rule_id="SR-999",
            title="SR-999",
            severity="MEDIUM",
            status=FindingStatus.NEW,
            source=FindingSource.AUTO,
        )
        data = serialize_finding(finding)
        self.assertEqual(data["title"], "SR-999")

    def test_serialize_finding_trigger_entity_id_is_string_or_none(self):
        entity_id = uuid.uuid4()
        finding = Finding.objects.create(
            case=self.case,
            rule_id="SR-010",
            title="Test",
            severity="MEDIUM",
            status=FindingStatus.NEW,
            source=FindingSource.AUTO,
            trigger_entity_id=entity_id,
        )
        data = serialize_finding(finding)
        self.assertEqual(data["trigger_entity_id"], str(entity_id))

    def test_serialize_finding_trigger_entity_id_none_when_not_set(self):
        finding = _make_finding(self.case)
        data = serialize_finding(finding)
        self.assertIsNone(data["trigger_entity_id"])


# ---------------------------------------------------------------------------
# SignalUpdateSerializer
# ---------------------------------------------------------------------------


class FindingUpdateSerializerTests(TestCase):
    def setUp(self):
        self.case = _make_case()
        self.finding = _make_finding(self.case, rule_id="SR-010")

    def test_confirm_finding(self):
        s = FindingUpdateSerializer(data={"status": "CONFIRMED"}, instance=self.finding)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.CONFIRMED)

    def test_escalate_finding(self):
        s = FindingUpdateSerializer(data={"status": "CONFIRMED"}, instance=self.finding)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.CONFIRMED)

    def test_dismiss_with_note(self):
        s = FindingUpdateSerializer(
            data={"status": "DISMISSED", "investigator_note": "Not relevant to this case."},
            instance=self.finding,
        )
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.DISMISSED)
        self.assertEqual(self.finding.investigator_note, "Not relevant to this case.")

    def test_dismiss_without_note_is_invalid(self):
        s = FindingUpdateSerializer(data={"status": "DISMISSED"}, instance=self.finding)
        self.assertFalse(s.is_valid())
        self.assertIn("investigator_note", s.errors)

    def test_empty_payload_is_invalid(self):
        s = FindingUpdateSerializer(data={}, instance=self.finding)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_invalid_status_value_is_rejected(self):
        s = FindingUpdateSerializer(data={"status": "ARCHIVED"}, instance=self.finding)
        self.assertFalse(s.is_valid())
        self.assertIn("status", s.errors)

    def test_unexpected_field_is_rejected(self):
        s = FindingUpdateSerializer(data={"severity": "LOW"}, instance=self.finding)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_no_instance_raises_error(self):
        s = FindingUpdateSerializer(data={"status": "CONFIRMED"}, instance=None)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_data_property_returns_serialized_finding(self):
        s = FindingUpdateSerializer(data={"status": "CONFIRMED"}, instance=self.finding)
        s.is_valid()
        s.save()
        data = s.data
        self.assertIn("rule_id", data)
        self.assertEqual(data["status"], "CONFIRMED")


# ---------------------------------------------------------------------------
# Signal API — Collection (GET)
# ---------------------------------------------------------------------------


class FindingCollectionApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = _make_case()
        self.url = reverse("api_case_finding_collection", args=[self.case.pk])

    def test_returns_empty_list_when_no_findings(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_returns_all_findings_for_case(self):
        _make_finding(self.case, rule_id="SR-003")
        _make_finding(self.case, rule_id="SR-010")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_does_not_return_findings_from_other_cases(self):
        other_case = _make_case("Other Case")
        _make_finding(other_case, rule_id="SR-003")

        response = self.client.get(self.url)

        self.assertEqual(response.json()["count"], 0)

    def test_filters_by_status(self):
        _make_finding(self.case, rule_id="SR-003", status=FindingStatus.NEW)
        _make_finding(self.case, rule_id="SR-010", status=FindingStatus.DISMISSED)

        response = self.client.get(self.url, {"status": "NEW"})

        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["rule_id"], "SR-003")

    def test_filters_by_severity(self):
        _make_finding(self.case, rule_id="SR-003", severity=Severity.CRITICAL)
        _make_finding(self.case, rule_id="SR-010", severity=Severity.MEDIUM)

        response = self.client.get(self.url, {"severity": "CRITICAL"})

        self.assertEqual(response.json()["count"], 1)

    def test_filters_by_rule_id(self):
        _make_finding(self.case, rule_id="SR-003")
        _make_finding(self.case, rule_id="SR-010")

        response = self.client.get(self.url, {"rule_id": "SR-010"})

        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["rule_id"], "SR-010")

    def test_invalid_status_filter_returns_400(self):
        response = self.client.get(self.url, {"status": "INVALID"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_severity_filter_returns_400(self):
        response = self.client.get(self.url, {"severity": "EXTREME"})
        self.assertEqual(response.status_code, 400)

    def test_pagination_limit_offset(self):
        for i in range(5):
            _make_finding(self.case, rule_id="SR-010")

        response = self.client.get(self.url, {"limit": "2", "offset": "0"})

        data = response.json()
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["next_offset"], 2)

    def test_404_for_unknown_case(self):
        url = reverse("api_case_finding_collection", args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        response = self.client.post(self.url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)

    def test_response_contains_expected_fields(self):
        _make_finding(self.case, rule_id="SR-003")

        response = self.client.get(self.url)

        result = response.json()["results"][0]
        for key in (
            "id",
            "rule_id",
            "severity",
            "status",
            "title",
            "description",
            "narrative",
            "evidence_weight",
            "source",
            "trigger_entity_id",
            "trigger_doc_id",
            "investigator_note",
            "legal_refs",
            "created_at",
        ):
            self.assertIn(key, result)


# ---------------------------------------------------------------------------
# Signal API — Detail (GET + PATCH)
# ---------------------------------------------------------------------------


class FindingDetailApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = _make_case()
        self.finding = _make_finding(self.case, rule_id="SR-005")
        self.url = reverse(
            "api_case_finding_detail",
            args=[self.case.pk, self.finding.pk],
        )

    def test_get_returns_finding(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.finding.pk))
        self.assertEqual(data["rule_id"], "SR-005")

    def test_404_for_unknown_finding(self):
        url = reverse("api_case_finding_detail", args=[self.case.pk, uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_finding_belongs_to_different_case(self):
        other_case = _make_case("Other")
        other_finding = _make_finding(other_case, rule_id="SR-003")
        url = reverse("api_case_finding_detail", args=[self.case.pk, other_finding.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_patch_confirms_finding(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "CONFIRMED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.CONFIRMED)

    def test_patch_needs_evidence_finding(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "NEEDS_EVIDENCE"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.NEEDS_EVIDENCE)

    def test_patch_dismisses_finding_with_note(self):
        response = self.client.patch(
            self.url,
            data=json.dumps(
                {
                    "status": "DISMISSED",
                    "investigator_note": "False positive — data entry error.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, FindingStatus.DISMISSED)
        self.assertEqual(self.finding.investigator_note, "False positive — data entry error.")

    def test_patch_dismiss_without_note_returns_400(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "DISMISSED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("investigator_note", response.json()["errors"])

    def test_patch_invalid_status_returns_400(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "ARCHIVED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_unexpected_field_returns_400(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"rule_id": "SR-999"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_returns_updated_finding(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "CONFIRMED"}),
            content_type="application/json",
        )
        data = response.json()
        self.assertEqual(data["status"], "CONFIRMED")
        self.assertEqual(data["id"], str(self.finding.pk))

    def test_delete_not_allowed(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# evaluate_document() integration
# ---------------------------------------------------------------------------


class EvaluateDocumentIntegrationTests(TestCase):
    """
    Smoke-test that evaluate_document() calls all four document-scoped rules
    in a single pass without errors.
    """

    def setUp(self):
        self.case = _make_case()

    def test_evaluate_document_runs_without_error_on_empty_case(self):
        doc = _make_document(self.case, doc_type="DEED", extracted_text="Transfer for $0.00.")
        result = evaluate_document(self.case, doc)
        # SR-005 should detect zero consideration
        rule_ids = {t.rule_id for t in result}
        self.assertIn("SR-005", rule_ids)

    def test_evaluate_case_runs_without_error_on_empty_case(self):
        result = evaluate_case(self.case)
        self.assertIsInstance(result, list)

    def test_evaluate_document_returns_list(self):
        doc = _make_document(self.case, extracted_text=None)
        result = evaluate_document(self.case, doc)
        self.assertIsInstance(result, list)
