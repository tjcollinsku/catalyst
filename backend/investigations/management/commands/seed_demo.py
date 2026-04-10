"""
seed_demo management command
============================
Creates a comprehensive demo case with realistic data that exercises every
part of the Catalyst system. The demo case showcases:
  - Multiple entity types (persons, organizations, properties)
  - Relationships and connections (family, business, board roles)
  - Financial data (FinancialSnapshots from 990 filings)
  - Property transactions with fraud patterns
  - Documents (metadata only—no actual files)
  - Findings generated from signal rules
  - Full fraud signal detection pipeline

The fictional scenario: "Bright Future Foundation"
  - 501(c)(3) nonprofit in Ohio
  - Founded 2015, revenue grew $85K → $4.2M (2016-2021)
  - Executive director married to board member (conflict of interest)
  - Related LLC: Mitchell Development Group (real estate transactions)
  - Property transactions at inflated/zero prices with related parties
  - Zero officer compensation despite $4M+ revenue
  - No conflict-of-interest policy
  - 990 Form says "Yes" to related-party transactions but no Schedule L filed

Usage:
    python manage.py seed_demo            # create demo case (idempotent)
    python manage.py seed_demo --reset    # delete & recreate
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from investigations.models import (
    Address,
    AddressType,
    AuditAction,
    AuditLog,
    Case,
    CaseStatus,
    Document,
    DocumentType,
    EvidenceWeight,
    ExtractionStatus,
    FinancialSnapshot,
    Finding,
    FindingDocument,
    FindingSource,
    FindingStatus,
    InvestigatorNote,
    OcrStatus,
    Organization,
    OrganizationStatus,
    OrganizationType,
    OrgDocument,
    Person,
    PersonOrganization,
    PersonRole,
    Property,
    PropertyTransaction,
    Relationship,
    RelationshipSource,
    RelationshipType,
    Severity,
    TransactionPartyType,
)


class Command(BaseCommand):
    help = (
        "Seed a comprehensive demo case with realistic fraud investigation "
        "data showcasing the full Catalyst pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the existing demo case before recreating it",
        )

    def handle(self, *args, **options):
        DEMO_CASE_NAME = "Bright Future Foundation Investigation"

        if options["reset"]:
            deleted, _ = Case.objects.filter(name=DEMO_CASE_NAME).delete()
            self.stdout.write(f"Deleted {deleted} existing demo case(s).")

        case, created = Case.objects.get_or_create(
            name=DEMO_CASE_NAME,
            defaults={
                "status": CaseStatus.ACTIVE,
                "notes": (
                    "Comprehensive demo case showcasing the full Catalyst fraud "
                    "investigation pipeline. Based on a fictional Ohio nonprofit "
                    "with rapid revenue growth, insider board relationships, and "
                    "related-party property transactions at inflated prices."
                ),
            },
        )

        if not created:
            self.stdout.write(
                self.style.WARNING(
                    f"Demo case already exists: {case.id}  "
                    f"(use --reset to recreate)"
                )
            )
            self.stdout.write(f"CASE_ID={case.id}")
            return

        with transaction.atomic():
            self._create_demo_data(case)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("✓ Demo case created successfully!")
        )
        self.stdout.write(f"CASE_ID={case.id}")
        self.stdout.write("")
        self.stdout.write("To explore the demo case:")
        self.stdout.write(
            f"  http://localhost:3000/cases/{case.id}"
        )

    def _create_demo_data(self, case: Case):
        """Create all demo entities, relationships, and findings."""

        # ────────────────────────────────────────────────────────────────
        # 1. ORGANIZATIONS
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating organizations...")
        bff, _ = Organization.objects.get_or_create(
            case=case,
            name="Bright Future Foundation",
            defaults={
                "ein": "31-1234567",
                "registration_state": "OH",
                "org_type": OrganizationType.CHARITY,
                "status": OrganizationStatus.ACTIVE,
                "address": "123 Oak Street, Columbus, OH 43215",
                "phone": "(614) 555-0100",
                "email": "info@brightfuture.org",
            },
        )

        mitchell_dev, _ = Organization.objects.get_or_create(
            case=case,
            name="Mitchell Development Group LLC",
            defaults={
                "registration_state": "OH",
                "org_type": OrganizationType.LLC,
                "status": OrganizationStatus.ACTIVE,
                "address": "456 Business Park Dr, Columbus, OH 43219",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ {bff.name}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  ✓ {mitchell_dev.name}")
        )

        # ────────────────────────────────────────────────────────────────
        # 2. PERSONS
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating persons...")
        sarah, _ = Person.objects.get_or_create(
            case=case,
            full_name="Sarah Mitchell",
            defaults={
                "role_tags": [PersonRole.OFFICER],
                "address": "789 Maple Ave, Columbus, OH 43216",
                "email": "sarah@brightfuture.org",
                "phone": "(614) 555-0101",
            },
        )

        james, _ = Person.objects.get_or_create(
            case=case,
            full_name="James Mitchell",
            defaults={
                "role_tags": [PersonRole.BOARD_MEMBER],
                "address": "789 Maple Ave, Columbus, OH 43216",
            },
        )

        david, _ = Person.objects.get_or_create(
            case=case,
            full_name="David Chen",
            defaults={
                "role_tags": [PersonRole.BOARD_MEMBER, PersonRole.OFFICER],
                "email": "dchen@businessmail.com",
                "phone": "(614) 555-0102",
            },
        )

        rachel, _ = Person.objects.get_or_create(
            case=case,
            full_name="Rachel Torres",
            defaults={
                "role_tags": [PersonRole.BOARD_MEMBER],
            },
        )

        for person in [sarah, james, david, rachel]:
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ {person.full_name}")
            )

        # ────────────────────────────────────────────────────────────────
        # 3. PERSON-ORGANIZATION ROLES
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating person-organization roles...")
        PersonOrganization.objects.get_or_create(
            person=sarah,
            org=bff,
            role="Executive Director",
            defaults={"start_date": "2015-03-15"},
        )
        PersonOrganization.objects.get_or_create(
            person=sarah,
            org=mitchell_dev,
            role="Manager",
        )
        PersonOrganization.objects.get_or_create(
            person=james,
            org=bff,
            role="Board Member",
        )
        PersonOrganization.objects.get_or_create(
            person=james,
            org=mitchell_dev,
            role="Member",
        )
        PersonOrganization.objects.get_or_create(
            person=david,
            org=bff,
            role="Treasurer / Board Member",
        )
        PersonOrganization.objects.get_or_create(
            person=rachel,
            org=bff,
            role="Secretary / Board Member",
        )
        self.stdout.write(
            self.style.SUCCESS("  ✓ All person-org roles created")
        )

        # ────────────────────────────────────────────────────────────────
        # 4. RELATIONSHIPS (FAMILY)
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating relationships...")
        Relationship.objects.get_or_create(
            case=case,
            person_a=sarah,
            person_b=james,
            relationship_type=RelationshipType.SPOUSE,
            defaults={
                "source": RelationshipSource.INVESTIGATOR,
                "confidence": 1.0,
            },
        )
        self.stdout.write(
            self.style.SUCCESS("  ✓ Sarah ↔ James (SPOUSE)")
        )

        # ────────────────────────────────────────────────────────────────
        # 5. ADDRESSES
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating addresses...")
        oak_st_addr, _ = Address.objects.get_or_create(
            case=case,
            raw_text="1250 Oak Street, Columbus, OH 43215",
            defaults={
                "street": "1250 Oak Street",
                "city": "Columbus",
                "state": "OH",
                "zip_code": "43215",
                "county": "Franklin",
                "address_type": AddressType.PROPERTY,
            },
        )

        elm_ave_addr, _ = Address.objects.get_or_create(
            case=case,
            raw_text="875 Elm Avenue, Columbus, OH 43217",
            defaults={
                "street": "875 Elm Avenue",
                "city": "Columbus",
                "state": "OH",
                "zip_code": "43217",
                "county": "Franklin",
                "address_type": AddressType.PROPERTY,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ {oak_st_addr.raw_text}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  ✓ {elm_ave_addr.raw_text}")
        )

        # ────────────────────────────────────────────────────────────────
        # 6. PROPERTIES
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating properties...")
        prop_oak, _ = Property.objects.get_or_create(
            case=case,
            parcel_number="R-2024-0891",
            defaults={
                "address": "1250 Oak Street, Columbus, OH 43215",
                "county": "Franklin",
                "state": "OH",
                "assessed_value": Decimal("180000.00"),
                "purchase_price": Decimal("425000.00"),
                "property_type": "COMMERCIAL",
                "current_owner_name": "Bright Future Foundation",
                "normalized_address": oak_st_addr,
            },
        )

        prop_elm, _ = Property.objects.get_or_create(
            case=case,
            parcel_number="R-2024-1456",
            defaults={
                "address": "875 Elm Avenue, Columbus, OH 43217",
                "county": "Franklin",
                "state": "OH",
                "assessed_value": Decimal("220000.00"),
                "purchase_price": Decimal("0.00"),
                "property_type": "VACANT_LAND",
                "current_owner_name": "James Mitchell / Personal Trust",
                "normalized_address": elm_ave_addr,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ {prop_oak.address} (parcel {prop_oak.parcel_number})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ {prop_elm.address} (parcel {prop_elm.parcel_number})"
            )
        )

        # ────────────────────────────────────────────────────────────────
        # 7. PROPERTY TRANSACTIONS
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating property transactions...")

        # BFF bought 1250 Oak from Mitchell Dev at inflated price
        txn1, _ = PropertyTransaction.objects.get_or_create(
            property=prop_oak,
            transaction_date="2021-06-28",
            defaults={
                "buyer_id": bff.id,
                "buyer_type": TransactionPartyType.ORGANIZATION,
                "buyer_name": bff.name,
                "seller_id": mitchell_dev.id,
                "seller_type": TransactionPartyType.ORGANIZATION,
                "seller_name": mitchell_dev.name,
                "price": Decimal("425000.00"),
                "instrument_number": "2021-0045678",
            },
        )

        # Mitchell Dev transferred 875 Elm to James for $0
        txn2, _ = PropertyTransaction.objects.get_or_create(
            property=prop_elm,
            transaction_date="2021-08-15",
            defaults={
                "buyer_id": james.id,
                "buyer_type": TransactionPartyType.PERSON,
                "buyer_name": james.full_name,
                "seller_id": mitchell_dev.id,
                "seller_type": TransactionPartyType.ORGANIZATION,
                "seller_name": mitchell_dev.name,
                "price": Decimal("0.00"),
                "instrument_number": "2021-0058901",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "  ✓ BFF bought 1250 Oak from Mitchell Dev @ $425K "
                "(assessed: $180K)"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "  ✓ Mitchell Dev transferred 875 Elm to James @ $0"
            )
        )

        # ────────────────────────────────────────────────────────────────
        # 8. DOCUMENTS (Metadata Only)
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating document records...")

        # Create minimal document records (no actual files)
        docs_data = [
            {
                "filename": "BFF_Form990_2021.pdf",
                "display_name": "2021-12-31_BFF_IRS_990.pdf",
                "doc_type": DocumentType.IRS_990,
                "file_path": "/mnt/documents/990/2021/",
                "sha256_hash": "a" * 64,
                "file_size": 245000,
            },
            {
                "filename": "BFF_Form990_2020.pdf",
                "display_name": "2020-12-31_BFF_IRS_990.pdf",
                "doc_type": DocumentType.IRS_990,
                "file_path": "/mnt/documents/990/2020/",
                "sha256_hash": "b" * 64,
                "file_size": 238000,
            },
            {
                "filename": "Deed_1250_Oak_St.pdf",
                "display_name": "2021-06-28_Property_Deed_Oak.pdf",
                "doc_type": DocumentType.DEED,
                "file_path": "/mnt/documents/deeds/",
                "sha256_hash": "c" * 64,
                "file_size": 150000,
            },
            {
                "filename": "Deed_875_Elm_Ave.pdf",
                "display_name": "2021-08-15_Property_Deed_Elm.pdf",
                "doc_type": DocumentType.DEED,
                "file_path": "/mnt/documents/deeds/",
                "sha256_hash": "d" * 64,
                "file_size": 145000,
            },
            {
                "filename": "BFF_Articles_Incorporation.pdf",
                "display_name": "2015-03-15_BFF_Corp_Articles.pdf",
                "doc_type": DocumentType.CORP_FILING,
                "file_path": "/mnt/documents/corp/",
                "sha256_hash": "e" * 64,
                "file_size": 50000,
            },
            {
                "filename": "Mitchell_Dev_Formation.pdf",
                "display_name": "2019-01-20_Mitchell_Dev_LLC_Formation.pdf",
                "doc_type": DocumentType.CORP_FILING,
                "file_path": "/mnt/documents/corp/",
                "sha256_hash": "f" * 64,
                "file_size": 45000,
            },
            {
                "filename": "Ohio_AOS_Audit_2020.pdf",
                "display_name": "2020-11-10_Ohio_AOS_Audit_Report.pdf",
                "doc_type": DocumentType.AUDITOR,
                "file_path": "/mnt/documents/government/",
                "sha256_hash": "1" * 64,
                "file_size": 85000,
            },
        ]

        docs = {}
        for doc_data in docs_data:
            doc, _ = Document.objects.get_or_create(
                case=case,
                filename=doc_data["filename"],
                defaults={
                    "display_name": doc_data["display_name"],
                    "doc_type": doc_data["doc_type"],
                    "file_path": doc_data["file_path"],
                    "sha256_hash": doc_data["sha256_hash"],
                    "file_size": doc_data["file_size"],
                    "ocr_status": OcrStatus.COMPLETED,
                    "extraction_status": ExtractionStatus.COMPLETED,
                },
            )
            docs[doc_data["filename"]] = doc
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ {doc_data['display_name']}")
            )

        # ────────────────────────────────────────────────────────────────
        # 9. DOCUMENT LINKS
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Linking documents to entities...")

        # Link organizations to documents
        OrgDocument.objects.get_or_create(
            org=bff,
            document=docs["BFF_Form990_2021.pdf"],
            defaults={"context_note": "Most recent 990 filing (2021 tax year)"},
        )
        OrgDocument.objects.get_or_create(
            org=bff,
            document=docs["BFF_Articles_Incorporation.pdf"],
            defaults={"context_note": "Formation documents (2015)"},
        )

        # Link property transactions to deed documents
        FindingDocument.objects.get_or_create(
            document=docs["Deed_1250_Oak_St.pdf"],
            defaults={
                "finding": None,
                "page_reference": "Page 1",
                "context_note": "Proof of BFF purchase from Mitchell Dev",
            },
        )

        self.stdout.write(
            self.style.SUCCESS("  ✓ Documents linked to entities")
        )

        # ────────────────────────────────────────────────────────────────
        # 10. FINANCIAL SNAPSHOTS (990 Data)
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating financial snapshots...")

        snapshot_data = [
            {
                "tax_year": 2016,
                "total_revenue": 85000,
                "total_expenses": 72000,
                "net_assets_eoy": 43000,
            },
            {
                "tax_year": 2017,
                "total_revenue": 156000,
                "total_expenses": 141000,
                "net_assets_eoy": 58000,
            },
            {
                "tax_year": 2018,
                "total_revenue": 890000,
                "total_expenses": 845000,
                "net_assets_eoy": 103000,
            },
            {
                "tax_year": 2019,
                "total_revenue": 1650000,
                "total_expenses": 1580000,
                "net_assets_eoy": 173000,
            },
            {
                "tax_year": 2020,
                "total_revenue": 2800000,
                "total_expenses": 2720000,
                "net_assets_eoy": 253000,
            },
            {
                "tax_year": 2021,
                "total_revenue": 4200000,
                "total_expenses": 4050000,
                "net_assets_eoy": 403000,
            },
        ]

        for snap_data in snapshot_data:
            doc = docs.get("BFF_Form990_2021.pdf") if (
                snap_data["tax_year"] == 2021
            ) else docs.get("BFF_Form990_2020.pdf")

            FinancialSnapshot.objects.get_or_create(
                document=doc or docs["BFF_Form990_2021.pdf"],
                case=case,
                tax_year=snap_data["tax_year"],
                defaults={
                    "organization": bff,
                    "ein": "31-1234567",
                    "form_type": "990",
                    "total_contributions": int(snap_data["total_revenue"]),
                    "program_service_revenue": 0,
                    "investment_income": 0,
                    "other_revenue": 0,
                    "total_revenue": snap_data["total_revenue"],
                    "grants_paid": int(
                        snap_data["total_revenue"] * Decimal("0.15")
                    ),
                    "salaries_and_compensation": int(
                        snap_data["total_revenue"] * Decimal("0.0")
                    ),
                    "professional_fundraising": int(
                        snap_data["total_revenue"] * Decimal("0.10")
                    ),
                    "other_expenses": int(
                        snap_data["total_revenue"] * Decimal("0.25")
                    ),
                    "total_expenses": snap_data["total_expenses"],
                    "net_assets_eoy": snap_data["net_assets_eoy"],
                    "num_employees": 2,
                    "num_voting_members": 4,
                    "officer_compensation_total": 0,
                    "source": "EXTRACTED",
                    "confidence": 1.0,
                },
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ 990 {snap_data['tax_year']}: "
                    f"${snap_data['total_revenue']:,} revenue"
                )
            )

        # ────────────────────────────────────────────────────────────────
        # 11. FINDINGS (Fraud Signals)
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating findings...")

        findings_data = [
            {
                "rule_id": "SR-003",
                "title": "VALUATION_ANOMALY — Property purchased at 136% above "
                "assessed value",
                "description": (
                    "1250 Oak Street assessed at $180,000 but purchased by "
                    "Bright Future Foundation from Mitchell Development Group "
                    "for $425,000 on 2021-06-28. Price deviation is 136% above "
                    "assessed value, suggesting either inflated price or "
                    "artificially depressed assessment."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.DOCUMENTED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "County assessor records show 1250 Oak Street with a fair "
                    "market assessment of $180,000. County recorder deed "
                    "records (instrument #2021-0045678) show BFF purchased the "
                    "property for $425,000 from Mitchell Development Group, a "
                    "company where BFF's Executive Director (Sarah Mitchell) is "
                    "listed as manager. The 136% price premium is consistent "
                    "with asset stripping or self-dealing."
                ),
                "legal_refs": ["26 U.S.C. § 4941", "ORC § 1702.33"],
                "trigger_entity_id": bff.id,
            },
            {
                "rule_id": "SR-005",
                "title": "ZERO_CONSIDERATION — Property transferred for $0 "
                "between related parties",
                "description": (
                    "875 Elm Avenue transferred by Mitchell Development Group "
                    "to James Mitchell (board member) for zero consideration on "
                    "2021-08-15. A zero-consideration transfer to a family "
                    "member of the charity's executive leadership suggests "
                    "asset stripping or undisclosed self-dealing."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.TRACED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "Deed records (instrument #2021-0058901) show 875 Elm Avenue "
                    "transferred from Mitchell Development Group (entity controlled "
                    "by insiders) to James Mitchell for $0. James Mitchell is a "
                    "board member and spouse of Sarah Mitchell (ED). This is a "
                    "classic insider swap: Mitchell Dev transfers charity-adjacent "
                    "property to insider with no compensation."
                ),
                "legal_refs": ["26 U.S.C. § 4941", "18 U.S.C. § 666"],
                "trigger_entity_id": james.id,
            },
            {
                "rule_id": "SR-006",
                "title": "SCHEDULE_L_MISSING — 990 Part IV Line 28 answered "
                "'Yes' but no Schedule L attached",
                "description": (
                    "Form 990 (2021) Part IV Line 28 (Related organization "
                    "transactions) answered 'Yes', indicating the organization "
                    "had related-party transactions, but Schedule L (Transactions "
                    "With Interested Persons) was not filed, which is required "
                    "by IRS regulations."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.DOCUMENTED,
                "source": FindingSource.AUTO,
                "legal_refs": ["26 U.S.C. § 6011", "IRS Form 990 Instructions"],
                "trigger_entity_id": bff.id,
            },
            {
                "rule_id": "SR-012",
                "title": "NO_COI_POLICY — Organization lacks conflict-of-interest "
                "policy despite material revenue",
                "description": (
                    "Bright Future Foundation is a $4.2M revenue organization with "
                    "board members having direct family relationships and business "
                    "interests, yet no conflict-of-interest policy is documented "
                    "in the case file or mentioned in 990 governance schedules."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.DOCUMENTED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "Executive Director Sarah Mitchell is married to board member "
                    "James Mitchell. Both are officers/managers of Mitchell "
                    "Development Group, which made property transactions with the "
                    "foundation. The absence of a COI policy despite these "
                    "relationships violates IRS best practices and state "
                    "nonprofit law."
                ),
                "legal_refs": ["ORC § 1702.33", "IRS Form 990 Part VI"],
                "trigger_entity_id": bff.id,
            },
            {
                "rule_id": "SR-013",
                "title": "ZERO_OFFICER_PAY — $0 officer compensation at $4.2M "
                "revenue organization",
                "description": (
                    "Form 990 (2021) Part VII shows $0 in officer compensation "
                    "for Bright Future Foundation despite $4.2M in total revenue. "
                    "This is implausible for a multi-million-dollar nonprofit and "
                    "suggests compensation may be routed through related entities."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.DOCUMENTED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "Part VII compensation table shows Executive Director and "
                    "board members with $0 compensation. At a $4.2M revenue "
                    "organization, $0 officer pay is implausible and suggests "
                    "that compensation is being paid through other entities "
                    "(likely Mitchell Development Group or management fee "
                    "arrangements)."
                ),
                "legal_refs": ["26 U.S.C. § 4958", "IRS Form 990 Part VII"],
                "trigger_entity_id": sarah.id,
            },
            {
                "rule_id": "SR-015",
                "title": "INSIDER_SWAP — Related party on both sides of "
                "property transaction",
                "description": (
                    "Sarah Mitchell (Executive Director) appears on both sides of "
                    "property transactions: (1) BFF purchased 1250 Oak for $425K "
                    "from Mitchell Development Group (where she is manager), and "
                    "(2) her spouse James Mitchell received 875 Elm for $0 from "
                    "the same company. This is a classic insider swap pattern."
                ),
                "severity": Severity.CRITICAL,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.TRACED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "The transaction chain shows: (1) Mitchell Dev buys property "
                    "X, transfers it to BFF at inflated price (Sarah as manager); "
                    "(2) Mitchell Dev has property Y, transfers it to James "
                    "(Sarah's spouse) for $0. Sarah and James are the key "
                    "insiders in both Mitchell Dev and BFF leadership. This is "
                    "a textbook insider swap."
                ),
                "legal_refs": ["26 U.S.C. § 4941", "18 U.S.C. § 666"],
                "trigger_entity_id": sarah.id,
            },
            {
                "rule_id": "SR-021",
                "title": "REVENUE_SPIKE — Year-over-year revenue increase "
                "exceeds 100%",
                "description": (
                    "Bright Future Foundation's revenue increased from $156,000 "
                    "(2017) to $890,000 (2018), a 471% increase. From 2019 to "
                    "2020, revenue jumped from $1.65M to $2.8M (70% increase). "
                    "Sustained 70%+ YoY growth is unusual and warrants review of "
                    "revenue sources."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.NEEDS_EVIDENCE,
                "evidence_weight": EvidenceWeight.DIRECTIONAL,
                "source": FindingSource.AUTO,
                "legal_refs": ["IRS Form 990 Part I"],
                "trigger_entity_id": bff.id,
            },
            {
                "rule_id": "SR-025",
                "title": "FALSE_DISCLOSURE — 990 Form denies related-party "
                "transactions; evidence contradicts",
                "description": (
                    "Form 990 Part IV contains contradictory statements: "
                    "Line 28 (related-party transactions) answered 'Yes', but "
                    "elsewhere the form claims no material transactions with "
                    "insiders. County recorder records show property transfers "
                    "between the foundation and insider-controlled entities."
                ),
                "severity": Severity.CRITICAL,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.TRACED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "Form 990 Part IV Line 28 = Yes (org had related-party txns) "
                    "but the narrative sections claim arm's-length dealing. "
                    "County recorder records, however, show: (1) BFF bought "
                    "1250 Oak from Mitchell Dev (insider company); (2) James "
                    "Mitchell (board member) received property from Mitchell Dev. "
                    "The form misrepresents the extent and nature of insider "
                    "transactions."
                ),
                "legal_refs": ["26 U.S.C. § 6652", "18 U.S.C. § 1001"],
                "trigger_entity_id": bff.id,
            },
            {
                "rule_id": "SR-029",
                "title": "LOW_PROGRAM_RATIO — Program expenses only 38% of total",
                "description": (
                    "In 2021, Bright Future Foundation spent approximately 38% "
                    "of total expenses on program services. IRS guidance and state "
                    "law generally recommend ≥50% for nonprofits of this type and "
                    "size. Low program ratio suggests overhead bloat or diversion "
                    "of funds."
                ),
                "severity": Severity.HIGH,
                "status": FindingStatus.CONFIRMED,
                "evidence_weight": EvidenceWeight.DOCUMENTED,
                "source": FindingSource.AUTO,
                "narrative": (
                    "Form 990 Part I (2021): Total expenses $4.05M, grants paid "
                    "$630K (15%), admin/salaries $1.62M (40%), other $0.81M (20%), "
                    "fundraising $0.42M (10%), program $1.50M (38%). The 38% "
                    "program ratio is below recommended thresholds. The fact that "
                    "$0 in salaries are reported but the organization clearly has "
                    "staff suggests compensation is routed elsewhere."
                ),
                "legal_refs": ["ORC § 1702.33", "IRS Form 990 Part I"],
                "trigger_entity_id": bff.id,
            },
        ]

        for finding_data in findings_data:
            trigger_entity_id = finding_data.pop("trigger_entity_id", None)
            finding, _ = Finding.objects.get_or_create(
                case=case,
                rule_id=finding_data["rule_id"],
                defaults=finding_data,
            )

            if trigger_entity_id:
                finding.trigger_entity_id = trigger_entity_id
                finding.save()

            # Link to trigger document if available
            if finding_data["rule_id"] in ["SR-003", "SR-005"]:
                doc = docs.get("Deed_1250_Oak_St.pdf") if (
                    finding_data["rule_id"] == "SR-003"
                ) else docs.get("Deed_875_Elm_Ave.pdf")
                if doc:
                    FindingDocument.objects.get_or_create(
                        finding=finding,
                        document=doc,
                        defaults={
                            "page_reference": "Page 1",
                            "context_note": "Transaction evidence",
                        },
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ {finding_data['rule_id']}: {finding_data['title'][:50]}"
                )
            )

        # ────────────────────────────────────────────────────────────────
        # 12. INVESTIGATOR NOTES
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating investigator notes...")

        InvestigatorNote.objects.get_or_create(
            case=case,
            target_type="Case",
            defaults={
                "note_text": (
                    "Initial case opened based on IRS Form 990 anomalies: "
                    "zero officer compensation, rapid revenue growth (85K→4.2M), "
                    "and suspicious property transactions. County recorder search "
                    "revealed two properties transferred between foundation and "
                    "insider-controlled LLC. Related parties (ED + spouse) are "
                    "officers of both entities. Further investigation needed on "
                    "revenue sources and asset appraisals."
                ),
            },
        )

        InvestigatorNote.objects.get_or_create(
            case=case,
            target_type="Organization",
            target_id=bff.id,
            defaults={
                "note_text": (
                    "Two of four board members are married to each other "
                    "(Sarah & James Mitchell). Both are also officers/managers of "
                    "Mitchell Development Group, which has made property deals "
                    "with the foundation. COI policy is absent."
                ),
            },
        )

        InvestigatorNote.objects.get_or_create(
            case=case,
            target_type="Person",
            target_id=sarah.id,
            defaults={
                "note_text": (
                    "Sarah Mitchell is ED of BFF and Manager of Mitchell Dev. "
                    "Her spouse James is board member at BFF and Member of "
                    "Mitchell Dev. Need to pull Sarah's personal tax returns to "
                    "see if she's claiming self-employment income or rental income "
                    "from these entities."
                ),
            },
        )

        self.stdout.write(
            self.style.SUCCESS("  ✓ Investigator notes created")
        )

        # ────────────────────────────────────────────────────────────────
        # 13. AUDIT LOG ENTRIES
        # ────────────────────────────────────────────────────────────────

        self.stdout.write("Creating audit log entries...")

        AuditLog.log(
            action=AuditAction.RECORD_CREATED,
            table_name="cases",
            record_id=case.id,
            case_id=case.id,
            performed_by="seed_demo",
            notes="Demo case created",
        )

        AuditLog.log(
            action=AuditAction.FINDING_CREATED,
            table_name="findings",
            case_id=case.id,
            performed_by="seed_demo",
            notes=f"Created {len(findings_data)} demo findings",
        )

        self.stdout.write(
            self.style.SUCCESS("  ✓ Audit log entries created")
        )
