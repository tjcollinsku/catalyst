"""
Tests for the Signal Detection Engine.

Covers:
  - Rule registry metadata (RULE_REGISTRY)
  - Each rule evaluator: SR-001 through SR-010
  - persist_signals() deduplication logic
  - serialize_signal() output structure
  - SignalUpdateSerializer validation and save
  - GET /api/cases/<pk>/signals/ (list, filters, pagination, sorting)
  - GET /api/cases/<pk>/signals/<signal_id>/ (detail)
  - PATCH /api/cases/<pk>/signals/<signal_id>/ (confirm, dismiss, escalate)
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Case,
    Document,
    DocumentType,
    FinancialInstrument,
    InstrumentType,
    OcrStatus,
    Organization,
    OrganizationType,
    Person,
    Property,
    Signal,
    SignalSeverity,
    SignalStatus,
)
from .serializers import SignalUpdateSerializer, serialize_signal
from .signal_rules import (
    RULE_REGISTRY,
    SignalTrigger,
    evaluate_case,
    evaluate_document,
    evaluate_sr001_deceased_signer,
    evaluate_sr002_entity_predates_formation,
    evaluate_sr003_valuation_anomaly,
    evaluate_sr004_ucc_burst,
    evaluate_sr005_zero_consideration,
    evaluate_sr006_990_schedule_l,
    evaluate_sr007_permit_owner_mismatch,
    evaluate_sr008_survey_before_purchase,
    evaluate_sr009_single_contractor,
    evaluate_sr010_missing_990,
    persist_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(name="Test Case"):
    return Case.objects.create(name=name)


def _make_document(case, *, doc_type="OTHER", extracted_text=None, filename="doc.pdf",
                   doc_subtype=""):
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


def _make_signal(case, rule_id="SR-001", severity=SignalSeverity.CRITICAL,
                 status=SignalStatus.OPEN):
    return Signal.objects.create(
        case=case,
        rule_id=rule_id,
        severity=severity,
        status=status,
    )


# ---------------------------------------------------------------------------
# Rule Registry
# ---------------------------------------------------------------------------

class RuleRegistryTests(TestCase):
    """Ensure all 10 SR rules are registered with correct severity values."""

    EXPECTED = {
        "SR-001": "CRITICAL",
        "SR-002": "CRITICAL",
        "SR-003": "HIGH",
        "SR-004": "HIGH",
        "SR-005": "HIGH",
        "SR-006": "HIGH",
        "SR-007": "HIGH",
        "SR-008": "MEDIUM",
        "SR-009": "MEDIUM",
        "SR-010": "MEDIUM",
    }

    def test_all_rules_present(self):
        for rule_id in self.EXPECTED:
            with self.subTest(rule_id=rule_id):
                self.assertIn(rule_id, RULE_REGISTRY)

    def test_rule_severities(self):
        for rule_id, expected_severity in self.EXPECTED.items():
            with self.subTest(rule_id=rule_id):
                self.assertEqual(
                    RULE_REGISTRY[rule_id].severity, expected_severity)

    def test_rules_have_title_and_description(self):
        for rule_id, info in RULE_REGISTRY.items():
            with self.subTest(rule_id=rule_id):
                self.assertTrue(info.title, f"{rule_id} has empty title")
                self.assertTrue(info.description,
                                f"{rule_id} has empty description")


# ---------------------------------------------------------------------------
# SR-001 — Deceased Signer
# ---------------------------------------------------------------------------

class SR001DeceasedSignerTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def _doc_with_text(self, text):
        return _make_document(self.case, extracted_text=text)

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_fires_when_date_after_death_and_name_in_text(self, mock_dates):
        death_date = date(2020, 1, 1)
        mock_dates.return_value = [date(2021, 6, 15)]
        _make_person(self.case, "John Smith", date_of_death=death_date)
        doc = self._doc_with_text("Signed by John Smith on the date above.")

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-001")
        self.assertEqual(result[0].severity, "CRITICAL")
        self.assertEqual(result[0].trigger_doc, doc)
        self.assertIn("Smith", result[0].detected_summary)

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_person_has_no_death_date(self, mock_dates):
        mock_dates.return_value = [date(2021, 6, 15)]
        _make_person(self.case, "John Smith")
        doc = self._doc_with_text("Signed by John Smith.")

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(result, [])

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_name_absent_from_text(self, mock_dates):
        mock_dates.return_value = [date(2021, 6, 15)]
        _make_person(self.case, "John Smith", date_of_death=date(2020, 1, 1))
        doc = self._doc_with_text("Signed by Jane Doe, an unrelated party.")

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(result, [])

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_all_doc_dates_before_death(self, mock_dates):
        mock_dates.return_value = [date(2019, 5, 1)]
        _make_person(self.case, "John Smith", date_of_death=date(2020, 1, 1))
        doc = self._doc_with_text("Signed by John Smith on 2019-05-01.")

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_document_has_no_text(self):
        _make_person(self.case, "John Smith", date_of_death=date(2020, 1, 1))
        doc = _make_document(self.case, extracted_text=None)

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(result, [])

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_one_signal_per_deceased_person_per_document(self, mock_dates):
        """Even with multiple post-death dates in the doc, only one trigger per person."""
        mock_dates.return_value = [date(2021, 1, 1), date(2022, 3, 1)]
        _make_person(self.case, "John Smith", date_of_death=date(2020, 1, 1))
        doc = self._doc_with_text("John Smith signed.")

        result = evaluate_sr001_deceased_signer(self.case, doc)

        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# SR-002 — Entity Predates Formation Date
# ---------------------------------------------------------------------------

class SR002EntityPredatesFormationTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_fires_when_doc_date_before_formation(self, mock_dates):
        formation = date(2019, 8, 1)
        mock_dates.return_value = [date(2017, 9, 15)]
        _make_org(self.case, "Do Good RE LLC", formation_date=formation)
        doc = _make_document(
            self.case, extracted_text="Grantee: Do Good RE LLC, recorded 2017-09-15.")

        result = evaluate_sr002_entity_predates_formation(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-002")
        self.assertIn("Do Good RE LLC", result[0].detected_summary)

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_org_has_no_formation_date(self, mock_dates):
        mock_dates.return_value = [date(2017, 9, 15)]
        _make_org(self.case, "Do Good RE LLC")
        doc = _make_document(
            self.case, extracted_text="Grantee: Do Good RE LLC.")

        result = evaluate_sr002_entity_predates_formation(self.case, doc)

        self.assertEqual(result, [])

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_org_name_absent(self, mock_dates):
        mock_dates.return_value = [date(2017, 9, 15)]
        _make_org(self.case, "Do Good RE LLC", formation_date=date(2019, 8, 1))
        doc = _make_document(
            self.case, extracted_text="Grantee: Another Company LLC.")

        result = evaluate_sr002_entity_predates_formation(self.case, doc)

        self.assertEqual(result, [])

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_doc_date_after_formation(self, mock_dates):
        mock_dates.return_value = [date(2020, 3, 1)]
        _make_org(self.case, "Do Good RE LLC", formation_date=date(2019, 8, 1))
        doc = _make_document(
            self.case, extracted_text="Grantee: Do Good RE LLC, recorded 2020-03-01.")

        result = evaluate_sr002_entity_predates_formation(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_document_text_is_empty(self):
        _make_org(self.case, "Do Good RE LLC", formation_date=date(2019, 8, 1))
        doc = _make_document(self.case, extracted_text=None)

        result = evaluate_sr002_entity_predates_formation(self.case, doc)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-003 — Valuation Anomaly
# ---------------------------------------------------------------------------

class SR003ValuationAnomalyTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def test_fires_when_purchase_price_exceeds_assessed_by_over_50pct(self):
        _make_property(self.case, purchase_price=Decimal(
            "200000"), assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-003")
        self.assertEqual(result[0].severity, "HIGH")

    def test_fires_when_purchase_price_below_assessed_by_over_50pct(self):
        _make_property(self.case, purchase_price=Decimal(
            "40000"), assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(len(result), 1)
        self.assertIn("below", result[0].detected_summary)

    def test_no_fire_when_deviation_exactly_50pct(self):
        # Exactly 50% — boundary should NOT fire (rule is >50%)
        _make_property(self.case, purchase_price=Decimal(
            "150000"), assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_deviation_below_50pct(self):
        _make_property(self.case, purchase_price=Decimal(
            "120000"), assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_assessed_value_is_zero(self):
        _make_property(self.case, purchase_price=Decimal(
            "100000"), assessed_value=Decimal("0"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_purchase_price_missing(self):
        _make_property(self.case, assessed_value=Decimal("100000"))

        result = evaluate_sr003_valuation_anomaly(self.case)

        self.assertEqual(result, [])

    def test_multiple_properties_each_produce_own_signal(self):
        _make_property(self.case, purchase_price=Decimal(
            "200000"), assessed_value=Decimal("100000"), parcel_number="P1")
        _make_property(self.case, purchase_price=Decimal(
            "300000"), assessed_value=Decimal("100000"), parcel_number="P2")

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
        doc = _make_document(self.case, doc_type="DEED",
                             extracted_text="The consideration for this deed is $0.00.")

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-005")

    def test_fires_on_deed_with_love_and_affection_language(self):
        doc = _make_document(self.case, doc_type="DEED",
                             extracted_text="Transferred for love and affection between family members.")

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_fires_on_deed_with_no_consideration_phrase(self):
        doc = _make_document(self.case, doc_type="DEED",
                             extracted_text="Transfer made for no consideration.")

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_fires_on_recorder_instrument_doc_type(self):
        doc = _make_document(self.case, doc_type="RECORDER_INSTRUMENT",
                             extracted_text="Nominal consideration only — $0.00 paid.")

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(len(result), 1)

    def test_no_fire_on_non_deed_doc_type(self):
        doc = _make_document(self.case, doc_type="IRS_990",
                             extracted_text="No consideration received for this transaction.")

        result = evaluate_sr005_zero_consideration(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_normal_consideration_in_deed(self):
        doc = _make_document(self.case, doc_type="DEED",
                             extracted_text="For and in consideration of $250,000.00 paid.")

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
        doc = _make_document(
            self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-006")

    def test_no_fire_when_schedule_l_also_present(self):
        text = "Part IV 28a Yes. See Schedule L for detail."
        doc = _make_document(
            self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_on_non_990_doc_type(self):
        text = "Part IV 28a Yes — this is not a 990."
        doc = _make_document(self.case, doc_type="DEED", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_990_has_no_yes_pattern(self):
        text = "This form 990 does not indicate any interested person transactions."
        doc = _make_document(
            self.case, doc_type="IRS_990", extracted_text=text)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])

    def test_no_fire_when_no_text(self):
        doc = _make_document(
            self.case, doc_type="IRS_990", extracted_text=None)

        result = evaluate_sr006_990_schedule_l(self.case, doc)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-007 — Building Permit Applicant Mismatch
# ---------------------------------------------------------------------------

class SR007PermitOwnerMismatchTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def test_fires_when_applicant_not_in_case_entities(self):
        _make_org(self.case, "Osgood CIC")
        _make_document(
            self.case,
            doc_type="BUILDING_PERMIT",
            extracted_text="Applicant: Unknown Stranger\nContractor: ABC Builds",
        )

        result = evaluate_sr007_permit_owner_mismatch(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-007")
        self.assertIn("Unknown Stranger", result[0].detected_summary)

    def test_no_fire_when_applicant_matches_case_org(self):
        _make_org(self.case, "Osgood CIC")
        _make_document(
            self.case,
            doc_type="BUILDING_PERMIT",
            extracted_text="Applicant: Osgood CIC\nWork to perform: roof replacement",
        )

        result = evaluate_sr007_permit_owner_mismatch(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_applicant_matches_case_person(self):
        _make_person(self.case, "John Homan")
        _make_document(
            self.case,
            doc_type="BUILDING_PERMIT",
            extracted_text="Applicant: John Homan\nWork: new construction",
        )

        result = evaluate_sr007_permit_owner_mismatch(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_no_permit_docs(self):
        _make_org(self.case, "Osgood CIC")
        result = evaluate_sr007_permit_owner_mismatch(self.case)
        self.assertEqual(result, [])

    def test_no_fire_when_no_applicant_pattern_in_permit(self):
        _make_org(self.case, "Osgood CIC")
        _make_document(
            self.case,
            doc_type="BUILDING_PERMIT",
            extracted_text="Permit number 12345. Work to be performed: grading.",
        )

        result = evaluate_sr007_permit_owner_mismatch(self.case)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-008 — Survey Before Purchase
# ---------------------------------------------------------------------------

class SR008SurveyBeforePurchaseTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_fires_when_survey_date_more_than_90_days_before_instrument(self, mock_dates):
        survey_date = date(2023, 8, 1)
        instrument_date = date(2024, 1, 15)  # 167 days gap
        mock_dates.return_value = [survey_date]
        _make_document(self.case, filename="boundary_survey.pdf",
                       extracted_text="Survey completed on the above date.")
        FinancialInstrument.objects.create(
            case=self.case,
            instrument_type=InstrumentType.OTHER,
            filing_date=instrument_date,
        )

        result = evaluate_sr008_survey_before_purchase(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-008")

    @patch("investigations.signal_rules._extract_dates_from_text")
    def test_no_fire_when_gap_is_exactly_90_days(self, mock_dates):
        # 90 days is NOT > 90, so should not fire
        survey_date = date(2023, 8, 1)
        instrument_date = survey_date + timedelta(days=90)
        mock_dates.return_value = [survey_date]
        _make_document(self.case, filename="survey_plat.pdf",
                       extracted_text="Survey complete.")
        FinancialInstrument.objects.create(
            case=self.case, instrument_type=InstrumentType.OTHER,
            filing_date=instrument_date,
        )

        result = evaluate_sr008_survey_before_purchase(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_no_survey_docs(self):
        _make_document(self.case, filename="deed.pdf",
                       extracted_text="Deed text.")
        FinancialInstrument.objects.create(
            case=self.case, instrument_type=InstrumentType.OTHER,
            filing_date=date(2024, 1, 1),
        )

        result = evaluate_sr008_survey_before_purchase(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_no_financial_instruments(self):
        _make_document(self.case, filename="plat_map.pdf",
                       extracted_text="Survey boundary description.")

        result = evaluate_sr008_survey_before_purchase(self.case)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-009 — Single Contractor
# ---------------------------------------------------------------------------

class SR009SingleContractorTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def test_fires_when_same_contractor_on_all_permits(self):
        text_a = "Permit No. 001\nContractor: ABC Builds LLC\nWork: foundation"
        text_b = "Permit No. 002\nContractor: ABC Builds LLC\nWork: framing"
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text=text_a)
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text=text_b)

        result = evaluate_sr009_single_contractor(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-009")

    def test_no_fire_when_different_contractors(self):
        text_a = "Contractor: ABC Builds LLC"
        text_b = "Contractor: XYZ Construction Co"
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text=text_a)
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text=text_b)

        result = evaluate_sr009_single_contractor(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_only_one_permit(self):
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text="Contractor: ABC Builds LLC")

        result = evaluate_sr009_single_contractor(self.case)

        self.assertEqual(result, [])

    def test_no_fire_when_permits_lack_contractor_field(self):
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text="Permit No. 001 — work to be performed: grading.")
        _make_document(self.case, doc_type="BUILDING_PERMIT",
                       extracted_text="Permit No. 002 — work to be performed: paving.")

        result = evaluate_sr009_single_contractor(self.case)

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# SR-010 — Missing 990
# ---------------------------------------------------------------------------

class SR010Missing990Tests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def test_fires_when_charity_org_and_no_990_docs(self):
        _make_org(self.case, "Osgood Foundation", org_type="CHARITY")

        result = evaluate_sr010_missing_990(self.case)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_id, "SR-010")
        self.assertIn("Osgood Foundation", result[0].detected_summary)

    def test_no_fire_when_charity_has_990_doc(self):
        _make_org(self.case, "Osgood Foundation", org_type="CHARITY")
        _make_document(self.case, doc_type="IRS_990",
                       extracted_text="Form 990 filing.")

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

    def test_creates_new_signal(self):
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(len(created), 1)
        self.assertEqual(Signal.objects.count(), 1)

    def test_deduplicates_against_existing_open_signal(self):
        # Pre-create an OPEN signal with same key
        Signal.objects.create(
            case=self.case,
            rule_id="SR-010",
            severity=SignalSeverity.MEDIUM,
            trigger_entity_id=None,
            trigger_doc_id=None,
        )
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(created, [])
        self.assertEqual(Signal.objects.count(), 1)  # unchanged

    def test_does_not_deduplicate_against_dismissed_signal(self):
        # DISMISSED signals allow re-fire
        Signal.objects.create(
            case=self.case,
            rule_id="SR-010",
            severity=SignalSeverity.MEDIUM,
            trigger_entity_id=None,
            trigger_doc_id=None,
            status=SignalStatus.DISMISSED,
        )
        triggers = [self._trigger()]
        created = persist_signals(self.case, triggers)
        self.assertEqual(len(created), 1)
        self.assertEqual(Signal.objects.count(), 2)

    def test_persisted_signal_has_correct_fields(self):
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
        signal = created[0]
        self.assertEqual(signal.rule_id, "SR-010")
        self.assertEqual(signal.severity, "MEDIUM")
        self.assertEqual(signal.status, SignalStatus.OPEN)
        self.assertEqual(signal.detected_summary, "No 990 found.")
        self.assertEqual(signal.trigger_entity_id, org.pk)
        self.assertIsNone(signal.trigger_doc_id)

    def test_empty_trigger_list_returns_empty(self):
        created = persist_signals(self.case, [])
        self.assertEqual(created, [])


# ---------------------------------------------------------------------------
# serialize_signal()
# ---------------------------------------------------------------------------

class SerializeSignalTests(TestCase):

    def setUp(self):
        self.case = _make_case()

    def test_serialize_signal_includes_expected_keys(self):
        signal = _make_signal(self.case, rule_id="SR-001")
        data = serialize_signal(signal)
        expected_keys = {
            "id", "rule_id", "severity", "status", "title", "description",
            "detected_summary", "trigger_entity_id", "trigger_doc_id",
            "investigator_note", "detected_at",
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_serialize_signal_title_comes_from_rule_registry(self):
        signal = _make_signal(self.case, rule_id="SR-001")
        data = serialize_signal(signal)
        self.assertEqual(data["title"], RULE_REGISTRY["SR-001"].title)

    def test_serialize_signal_unknown_rule_id_uses_rule_id_as_title(self):
        signal = Signal.objects.create(
            case=self.case,
            rule_id="SR-999",
            severity=SignalSeverity.LOW,
        )
        data = serialize_signal(signal)
        self.assertEqual(data["title"], "SR-999")
        self.assertEqual(data["description"], "")

    def test_serialize_signal_trigger_entity_id_is_string_or_none(self):
        entity_id = uuid.uuid4()
        signal = Signal.objects.create(
            case=self.case,
            rule_id="SR-010",
            severity=SignalSeverity.MEDIUM,
            trigger_entity_id=entity_id,
        )
        data = serialize_signal(signal)
        self.assertEqual(data["trigger_entity_id"], str(entity_id))

    def test_serialize_signal_trigger_entity_id_none_when_not_set(self):
        signal = _make_signal(self.case)
        data = serialize_signal(signal)
        self.assertIsNone(data["trigger_entity_id"])


# ---------------------------------------------------------------------------
# SignalUpdateSerializer
# ---------------------------------------------------------------------------

class SignalUpdateSerializerTests(TestCase):

    def setUp(self):
        self.case = _make_case()
        self.signal = _make_signal(self.case, rule_id="SR-010")

    def test_confirm_signal(self):
        s = SignalUpdateSerializer(
            data={"status": "CONFIRMED"}, instance=self.signal)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.CONFIRMED)

    def test_escalate_signal(self):
        s = SignalUpdateSerializer(
            data={"status": "ESCALATED"}, instance=self.signal)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.ESCALATED)

    def test_dismiss_with_note(self):
        s = SignalUpdateSerializer(
            data={"status": "DISMISSED",
                  "investigator_note": "Not relevant to this case."},
            instance=self.signal,
        )
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.DISMISSED)
        self.assertEqual(self.signal.investigator_note,
                         "Not relevant to this case.")

    def test_dismiss_without_note_is_invalid(self):
        s = SignalUpdateSerializer(
            data={"status": "DISMISSED"}, instance=self.signal)
        self.assertFalse(s.is_valid())
        self.assertIn("investigator_note", s.errors)

    def test_empty_payload_is_invalid(self):
        s = SignalUpdateSerializer(data={}, instance=self.signal)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_invalid_status_value_is_rejected(self):
        s = SignalUpdateSerializer(
            data={"status": "ARCHIVED"}, instance=self.signal)
        self.assertFalse(s.is_valid())
        self.assertIn("status", s.errors)

    def test_unexpected_field_is_rejected(self):
        s = SignalUpdateSerializer(
            data={"severity": "LOW"}, instance=self.signal)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_no_instance_raises_error(self):
        s = SignalUpdateSerializer(data={"status": "CONFIRMED"}, instance=None)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)

    def test_data_property_returns_serialized_signal(self):
        s = SignalUpdateSerializer(
            data={"status": "CONFIRMED"}, instance=self.signal)
        s.is_valid()
        s.save()
        data = s.data
        self.assertIn("rule_id", data)
        self.assertEqual(data["status"], "CONFIRMED")


# ---------------------------------------------------------------------------
# Signal API — Collection (GET)
# ---------------------------------------------------------------------------

class SignalCollectionApiTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.case = _make_case()
        self.url = reverse("api_case_signal_collection", args=[self.case.pk])

    def test_returns_empty_list_when_no_signals(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_returns_all_signals_for_case(self):
        _make_signal(self.case, rule_id="SR-001")
        _make_signal(self.case, rule_id="SR-010")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_does_not_return_signals_from_other_cases(self):
        other_case = _make_case("Other Case")
        _make_signal(other_case, rule_id="SR-001")

        response = self.client.get(self.url)

        self.assertEqual(response.json()["count"], 0)

    def test_filters_by_status(self):
        _make_signal(self.case, rule_id="SR-001", status=SignalStatus.OPEN)
        _make_signal(self.case, rule_id="SR-010",
                     status=SignalStatus.DISMISSED)

        response = self.client.get(self.url, {"status": "OPEN"})

        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["rule_id"], "SR-001")

    def test_filters_by_severity(self):
        _make_signal(self.case, rule_id="SR-001",
                     severity=SignalSeverity.CRITICAL)
        _make_signal(self.case, rule_id="SR-010",
                     severity=SignalSeverity.MEDIUM)

        response = self.client.get(self.url, {"severity": "CRITICAL"})

        self.assertEqual(response.json()["count"], 1)

    def test_filters_by_rule_id(self):
        _make_signal(self.case, rule_id="SR-001")
        _make_signal(self.case, rule_id="SR-010")

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
            _make_signal(self.case, rule_id="SR-010")

        response = self.client.get(self.url, {"limit": "2", "offset": "0"})

        data = response.json()
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["next_offset"], 2)

    def test_404_for_unknown_case(self):
        url = reverse("api_case_signal_collection", args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_post_not_allowed(self):
        response = self.client.post(
            self.url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)

    def test_response_contains_expected_fields(self):
        _make_signal(self.case, rule_id="SR-003")

        response = self.client.get(self.url)

        result = response.json()["results"][0]
        for key in ("id", "rule_id", "severity", "status", "title", "description",
                    "detected_summary", "trigger_entity_id", "trigger_doc_id",
                    "investigator_note", "detected_at"):
            self.assertIn(key, result)


# ---------------------------------------------------------------------------
# Signal API — Detail (GET + PATCH)
# ---------------------------------------------------------------------------

class SignalDetailApiTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.case = _make_case()
        self.signal = _make_signal(self.case, rule_id="SR-005")
        self.url = reverse(
            "api_case_signal_detail",
            args=[self.case.pk, self.signal.pk],
        )

    def test_get_returns_signal(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.signal.pk))
        self.assertEqual(data["rule_id"], "SR-005")

    def test_404_for_unknown_signal(self):
        url = reverse("api_case_signal_detail",
                      args=[self.case.pk, uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_signal_belongs_to_different_case(self):
        other_case = _make_case("Other")
        other_signal = _make_signal(other_case, rule_id="SR-001")
        url = reverse("api_case_signal_detail",
                      args=[self.case.pk, other_signal.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_patch_confirms_signal(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "CONFIRMED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.CONFIRMED)

    def test_patch_escalates_signal(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "ESCALATED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.ESCALATED)

    def test_patch_dismisses_signal_with_note(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({
                "status": "DISMISSED",
                "investigator_note": "False positive — data entry error.",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, SignalStatus.DISMISSED)
        self.assertEqual(self.signal.investigator_note,
                         "False positive — data entry error.")

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

    def test_patch_returns_updated_signal(self):
        response = self.client.patch(
            self.url,
            data=json.dumps({"status": "CONFIRMED"}),
            content_type="application/json",
        )
        data = response.json()
        self.assertEqual(data["status"], "CONFIRMED")
        self.assertEqual(data["id"], str(self.signal.pk))

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
        doc = _make_document(self.case, doc_type="DEED",
                             extracted_text="Transfer for $0.00.")
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
