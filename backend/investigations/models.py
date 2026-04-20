import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F
from django.utils import timezone


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CaseStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    REFERRED = "REFERRED", "Referred"
    CLOSED = "CLOSED", "Closed"


class DocumentType(models.TextChoices):
    DEED = "DEED", "Deed"
    PARCEL_RECORD = "PARCEL_RECORD", "Parcel Record"
    RECORDER_INSTRUMENT = "RECORDER_INSTRUMENT", "Recorder Instrument"
    MORTGAGE = "MORTGAGE", "Mortgage"
    LIEN = "LIEN", "Lien"
    UCC = "UCC", "UCC Filing"
    IRS_990 = "IRS_990", "IRS Form 990"
    IRS_990T = "IRS_990T", "IRS Form 990-T"
    BUILDING_PERMIT = "BUILDING_PERMIT", "Building Permit"
    CORP_FILING = "CORP_FILING", "Corporate Filing"
    SOS_FILING = "SOS_FILING", "SOS Filing"
    COURT_FILING = "COURT_FILING", "Court Filing"
    DEATH_RECORD = "DEATH_RECORD", "Death Record / Obituary"
    SUSPECTED_FORGERY = "SUSPECTED_FORGERY", "Suspected Forgery"
    WEB_ARCHIVE = "WEB_ARCHIVE", "Web Archive / Screenshot"
    REFERRAL_MEMO = "REFERRAL_MEMO", "Referral / Complaint Memo"
    AUDITOR = "AUDITOR", "Auditor"
    OCC_REPORT = "OCC_REPORT", "OCC Report"
    CIC_REPORT = "CIC_REPORT", "CIC Report"
    OTHER = "OTHER", "Other"


class OcrStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    NOT_NEEDED = "NOT_NEEDED", "Not needed"


class ExtractionStatus(models.TextChoices):
    """SEC-027/028: Track whether post-OCR analysis steps succeeded."""

    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    PARTIAL = "PARTIAL", "Partial — some steps failed"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped — no text available"


class OrganizationType(models.TextChoices):
    CHARITY = "CHARITY", "Charity / 501(c)(3)"
    LLC = "LLC", "LLC"
    CORPORATION = "CORPORATION", "Corporation"
    LLP = "LLP", "Limited Liability Partnership"
    PARTNERSHIP = "PARTNERSHIP", "General Partnership"
    SOLE_PROPRIETORSHIP = "SOLE_PROP", "Sole Proprietorship"
    LAND_TRUST = "LAND_TRUST", "Land Trust"
    FARM_LLC = "FARM_LLC", "Farm / Agricultural LLC"
    HMAIN_COMPANY = "HMAIN", "Hmain Company"
    FILM_PRODUCTION = "FILM_PROD", "Film / Media Production"
    GOVERNMENT = "GOVERNMENT", "Government"
    CIC = "CIC", "CIC"
    OTHER = "OTHER", "Other"


class OrganizationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DISSOLVED = "DISSOLVED", "Dissolved"
    REVOKED = "REVOKED", "Revoked"
    UNKNOWN = "UNKNOWN", "Unknown"


class InstrumentType(models.TextChoices):
    UCC_FILING = "UCC_FILING", "UCC filing"
    LIEN = "LIEN", "Lien"
    MORTGAGE = "MORTGAGE", "Mortgage"
    LOAN = "LOAN", "Loan"
    OTHER = "OTHER", "Other"


class PersonRole(models.TextChoices):
    BOARD_MEMBER = "BOARD_MEMBER", "Board member"
    OFFICER = "OFFICER", "Officer"
    REGISTERED_AGENT = "REGISTERED_AGENT", "Registered agent"
    INCORPORATOR = "INCORPORATOR", "Incorporator"
    SECURED_PARTY = "SECURED_PARTY", "Secured party"
    DEBTOR = "DEBTOR", "Debtor"
    SIGNER = "SIGNER", "Signer"
    GRANTOR = "GRANTOR", "Grantor"
    GRANTEE = "GRANTEE", "Grantee"
    DECEASED = "DECEASED", "Deceased"
    ATTORNEY = "ATTORNEY", "Attorney"
    NOTARY = "NOTARY", "Notary"
    TRUSTEE = "TRUSTEE", "Trustee"
    TAX_PREPARER = "TAX_PREPARER", "Tax preparer"
    CONTRACTOR = "CONTRACTOR", "Contractor"
    FAMILY_MEMBER = "FAMILY_MEMBER", "Family member"
    SUBJECT_OF_INVESTIGATION = "SUBJECT_OF_INVESTIGATION", "Subject of investigation"
    WITNESS = "WITNESS", "Witness"


class FindingStatus(models.TextChoices):
    NEW = "NEW", "New — auto-detected, not yet reviewed"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE", "Needs evidence"
    DISMISSED = "DISMISSED", "Dismissed — false positive"
    CONFIRMED = "CONFIRMED", "Confirmed — included in referral"


class EvidenceWeight(models.TextChoices):
    SPECULATIVE = "SPECULATIVE", "Speculative — pattern matched only"
    DIRECTIONAL = "DIRECTIONAL", "Directional — suggestive but unproven"
    DOCUMENTED = "DOCUMENTED", "Documented — supporting docs on file"
    TRACED = "TRACED", "Traced — full citation chain to source"


class FindingSource(models.TextChoices):
    AUTO = "AUTO", "Auto-detected by signal rules"
    MANUAL = "MANUAL", "Manually created by investigator"


class Severity(models.TextChoices):
    CRITICAL = "CRITICAL", "Critical"
    HIGH = "HIGH", "High"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"
    INFORMATIONAL = "INFORMATIONAL", "Informational"


class Case(UUIDPrimaryKeyModel):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=CaseStatus.choices, default=CaseStatus.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    referral_ref = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "cases"

    def __str__(self) -> str:
        return self.name


class Document(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="documents")
    filename = models.CharField(max_length=255)
    display_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Forensic canonical name: YYYY-MM-DD_Entity_DocType.ext. "
            "Generated automatically by the pipeline. Original filename "
            "preserved in 'filename' for chain-of-custody."
        ),
    )
    file_path = models.CharField(max_length=500)
    sha256_hash = models.CharField(max_length=64)
    file_size = models.BigIntegerField()
    doc_type = models.CharField(
        max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER
    )
    is_generated = models.BooleanField(
        default=False,
        help_text=(
            "True for outputs produced by Catalyst (memos, reports). "
            "False for source documents ingested as evidence."
        ),
    )
    doc_subtype = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional free-text subtype for additional classification detail.",
    )
    source_url = models.CharField(max_length=500, blank=True, null=True)
    uploaded_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    ocr_status = models.CharField(
        max_length=20, choices=OcrStatus.choices, default=OcrStatus.PENDING
    )
    extracted_text = models.TextField(blank=True, null=True)

    # SEC-027/028: Track post-OCR analysis pipeline results so the UI
    # can warn investigators when entity extraction or signal detection failed.
    extraction_status = models.CharField(
        max_length=20,
        choices=ExtractionStatus.choices,
        default=ExtractionStatus.PENDING,
        help_text="Status of entity extraction and signal detection pipeline.",
    )
    extraction_notes = models.TextField(
        blank=True,
        default="",
        help_text="Details about any extraction failures (which steps failed and why).",
    )

    ingestion_metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Chain-of-custody metadata captured at ingestion time. Includes: "
            "PDF author, creator software, producer, creation/modification dates, "
            "page count, encryption status, form detection. Stored as JSON for "
            "flexibility across document types. Never modified after initial capture."
        ),
    )

    class Meta:
        db_table = "documents"
        indexes = [models.Index(fields=["case"], name="idx_documents_case_id")]


class Person(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="persons")
    full_name = models.CharField(max_length=255)
    aliases = ArrayField(models.TextField(), blank=True, default=list)
    role_tags = ArrayField(
        models.CharField(max_length=50, choices=PersonRole.choices),
        blank=True,
        default=list,
    )
    address = models.CharField(max_length=500, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.CharField(max_length=255, blank=True, default="")
    tax_id = models.CharField(max_length=20, blank=True, default="", help_text="SSN, ITIN, or PTIN")
    date_of_death = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "persons"
        indexes = [models.Index(fields=["case"], name="idx_persons_case_id")]

    def __str__(self) -> str:
        return self.full_name

    def is_deceased(self) -> bool:
        return (PersonRole.DECEASED in self.role_tags) or (self.date_of_death is not None)


class Organization(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="organizations")
    name = models.CharField(max_length=255)
    org_type = models.CharField(
        max_length=20, choices=OrganizationType.choices, default=OrganizationType.OTHER
    )
    ein = models.CharField(max_length=20, blank=True, null=True)
    registration_state = models.CharField(max_length=2, blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=OrganizationStatus.choices, default=OrganizationStatus.UNKNOWN
    )
    address = models.CharField(max_length=500, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.CharField(max_length=255, blank=True, default="")
    formation_date = models.DateField(
        blank=True,
        null=True,
        help_text=(
            "Date the entity was legally formed per Secretary of State records."
            " Used for SR-002 signal detection."
        ),
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "organizations"
        indexes = [models.Index(fields=["case"], name="idx_organizations_case_id")]

    def __str__(self) -> str:
        return self.name


class Property(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="properties")
    parcel_number = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(
        max_length=2,
        blank=True,
        default="OH",
        help_text="State abbreviation. Defaults to OH for Ohio cases.",
    )
    assessed_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    valuation_delta = models.GeneratedField(
        expression=F("purchase_price") - F("assessed_value"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
        null=True,
    )
    acreage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Property size in acres, if known.",
    )
    property_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="E.g. RESIDENTIAL, COMMERCIAL, AGRICULTURAL, VACANT_LAND.",
    )
    current_owner_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Owner per most recent auditor/parcel record.",
    )
    # Link to normalized Address for nexus detection
    normalized_address = models.ForeignKey(
        "Address",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="properties",
        help_text="Link to normalized Address record for nexus detection.",
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "properties"
        indexes = [
            models.Index(fields=["case"], name="idx_properties_case_id"),
            models.Index(fields=["county"], name="idx_properties_county"),
            models.Index(fields=["state", "county"], name="idx_properties_state_county"),
        ]


class FinancialInstrument(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="financial_instruments")
    instrument_type = models.CharField(
        max_length=20, choices=InstrumentType.choices, default=InstrumentType.OTHER
    )
    filing_number = models.CharField(max_length=100, blank=True, null=True)
    filing_date = models.DateField(blank=True, null=True)
    signer = models.ForeignKey(
        Person, on_delete=models.SET_NULL, blank=True, null=True, related_name="signed_instruments"
    )
    secured_party_id = models.UUIDField(blank=True, null=True)
    debtor_id = models.UUIDField(blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    anomaly_flags = ArrayField(models.TextField(), blank=True, default=list)

    # ── UCC-specific fields (for lien analysis) ──────────────────────
    # In the Example Charity case, Example Lender filed blanket liens covering
    # "all farm equipment, livestock, crops, and proceeds" — this is a
    # major red flag when the debtor is also running a charity.
    collateral_description = models.TextField(
        blank=True,
        default="",
        help_text="UCC collateral description (e.g. 'all farm equipment, livestock').",
    )
    is_blanket_lien = models.BooleanField(
        default=False,
        help_text="True if filing covers 'all assets' or equivalent blanket language.",
    )
    lapse_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date the UCC filing lapses (typically 5 years from filing).",
    )
    continuation_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date a continuation statement was filed to extend the lien.",
    )
    amendment_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="INITIAL, AMENDMENT, CONTINUATION, TERMINATION, ASSIGNMENT.",
    )
    parent_filing = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="amendments",
        help_text="For amendments/continuations, links to the original filing.",
    )
    filing_state = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text="State where the UCC was filed (e.g. 'OH').",
    )
    # ── End UCC-specific fields ──────────────────────────────────────

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "financial_instruments"
        indexes = [
            models.Index(fields=["case"], name="idx_fin_instr_case_id"),
            models.Index(fields=["signer"], name="idx_fin_instr_signer"),
            models.Index(fields=["is_blanket_lien"], name="idx_fin_instr_blanket"),
        ]


class PersonDocument(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent pair uniqueness.
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="person_links")
    page_reference = models.CharField(max_length=100, blank=True, null=True)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "person_document"
        constraints = [
            models.UniqueConstraint(
                fields=["person", "document"], name="uniq_person_document_pair"
            ),
        ]
        indexes = [models.Index(fields=["document"], name="idx_person_document_doc")]


class OrgDocument(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent pair uniqueness.
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="org_links")
    page_reference = models.CharField(max_length=100, blank=True, null=True)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "org_document"
        constraints = [
            models.UniqueConstraint(fields=["org", "document"], name="uniq_org_document_pair")
        ]
        indexes = [models.Index(fields=["document"], name="idx_org_document_doc")]


class PersonOrganization(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent tuple uniqueness.
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="organization_roles")
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="person_roles")
    role = models.CharField(max_length=100)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "person_org"
        constraints = [
            models.UniqueConstraint(fields=["person", "org", "role"], name="uniq_person_org_role"),
        ]


class TransactionPartyType(models.TextChoices):
    PERSON = "PERSON", "Person"
    ORGANIZATION = "ORGANIZATION", "Organization"


class PropertyTransaction(UUIDPrimaryKeyModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="transactions")
    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="property_transactions",
    )
    transaction_date = models.DateField(blank=True, null=True)

    # Buyer fields — polymorphic: could be a Person or Organization
    buyer_id = models.UUIDField(blank=True, null=True)
    buyer_type = models.CharField(
        max_length=20,
        choices=TransactionPartyType.choices,
        blank=True,
        default="",
        help_text="Whether the buyer is a Person or Organization.",
    )
    buyer_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Denormalized buyer name for quick display.",
    )

    # Seller fields
    seller_id = models.UUIDField(blank=True, null=True)
    seller_type = models.CharField(
        max_length=20,
        choices=TransactionPartyType.choices,
        blank=True,
        default="",
        help_text="Whether the seller is a Person or Organization.",
    )
    seller_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Denormalized seller name for quick display.",
    )

    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    instrument_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Recorder instrument number from county records.",
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "property_transaction"
        indexes = [
            models.Index(fields=["property"], name="idx_prop_tx_property"),
            models.Index(fields=["transaction_date"], name="idx_prop_tx_date"),
            models.Index(fields=["buyer_id"], name="idx_prop_tx_buyer"),
            models.Index(fields=["seller_id"], name="idx_prop_tx_seller"),
        ]


# ──────────────────────────────────────────────────────────────────────
# NEW: Address model — enables ADDRESS_NEXUS signal detection
# ──────────────────────────────────────────────────────────────────────
#
# WHY: In the Example Charity case, 123 Main St appears on the charity's filings,
# Jay Example's personal records, AND Example Lender UCC filings. The old schema
# stored addresses as plain text on Person/Organization — no way to detect
# that three entities share the same address. This model normalizes addresses
# into their own table so we can run:
#
#   Address.objects.annotate(
#       entity_count=Count('person_addresses') + Count('org_addresses')
#   ).filter(entity_count__gte=2)
#
# → instantly surfaces every shared address in a case.
# ──────────────────────────────────────────────────────────────────────


class AddressType(models.TextChoices):
    MAILING = "MAILING", "Mailing address"
    REGISTERED = "REGISTERED", "Registered agent address"
    PROPERTY = "PROPERTY", "Property address"
    BUSINESS = "BUSINESS", "Business / operating address"
    RESIDENCE = "RESIDENCE", "Residential address"
    FILING = "FILING", "Address on filing"
    OTHER = "OTHER", "Other"


class Address(UUIDPrimaryKeyModel):
    """
    Normalized address record. Multiple entities can link to the same Address,
    which is exactly how the signal engine detects ADDRESS_NEXUS patterns.

    The raw_text field stores the address exactly as it appeared on the source
    document (chain-of-custody). The parsed fields (street, city, etc.) are
    used for deduplication and fuzzy matching.
    """

    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="addresses")
    raw_text = models.CharField(
        max_length=500,
        help_text="Address exactly as it appeared on the source document.",
    )
    street = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=2, blank=True, default="")
    zip_code = models.CharField(max_length=10, blank=True, default="")
    county = models.CharField(max_length=100, blank=True, default="")
    address_type = models.CharField(
        max_length=20, choices=AddressType.choices, default=AddressType.OTHER
    )
    first_seen_date = models.DateField(
        blank=True,
        null=True,
        help_text="Earliest document date where this address appeared.",
    )
    last_seen_date = models.DateField(
        blank=True,
        null=True,
        help_text="Most recent document date where this address appeared.",
    )
    source_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="addresses_sourced",
        help_text="Document where this address was first extracted from.",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "addresses"
        indexes = [
            models.Index(fields=["case"], name="idx_addresses_case"),
            models.Index(fields=["street", "city", "state"], name="idx_addresses_location"),
            models.Index(fields=["county"], name="idx_addresses_county"),
        ]

    def __str__(self) -> str:
        return self.raw_text or f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class PersonAddress(UUIDPrimaryKeyModel):
    """Links a Person to an Address with a role (mailing, residence, etc.)."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="address_links")
    address = models.ForeignKey(Address, on_delete=models.CASCADE, related_name="person_addresses")
    address_role = models.CharField(
        max_length=20, choices=AddressType.choices, default=AddressType.OTHER
    )
    effective_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    source_document = models.ForeignKey(Document, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        db_table = "person_address"
        constraints = [
            models.UniqueConstraint(
                fields=["person", "address", "address_role"],
                name="uniq_person_address_role",
            ),
        ]


class OrgAddress(UUIDPrimaryKeyModel):
    """Links an Organization to an Address (registered agent, mailing, etc.)."""

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="address_links")
    address = models.ForeignKey(Address, on_delete=models.CASCADE, related_name="org_addresses")
    address_role = models.CharField(
        max_length=20, choices=AddressType.choices, default=AddressType.OTHER
    )
    effective_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    source_document = models.ForeignKey(Document, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        db_table = "org_address"
        constraints = [
            models.UniqueConstraint(
                fields=["org", "address", "address_role"],
                name="uniq_org_address_role",
            ),
        ]


# ──────────────────────────────────────────────────────────────────────
# NEW: Relationship model — tracks person-to-person connections
# ──────────────────────────────────────────────────────────────────────
#
# WHY: In the Example Charity case, Jay Example (charity officer) is the SON of
# Ronald Example Sr. (deceased signer) and BROTHER of Ron Er. He's also
# MARRIED to someone who appears on LLCs. The old schema had no way to
# record these relationships — so the signal engine couldn't detect that
# a property buyer and the charity officer are family members (INSIDER_SWAP).
#
# The signal engine query becomes:
#   Relationship.objects.filter(
#       person_a__in=buyers, person_b__in=charity_officers,
#       relationship_type='FAMILY'
#   ).exists()
# → True means INSIDER_SWAP flag fires.
# ──────────────────────────────────────────────────────────────────────


class RelationshipType(models.TextChoices):
    FAMILY = "FAMILY", "Family member"
    SPOUSE = "SPOUSE", "Spouse"
    PARENT_CHILD = "PARENT_CHILD", "Parent / Child"
    SIBLING = "SIBLING", "Sibling"
    BUSINESS_PARTNER = "BUSINESS_PARTNER", "Business partner"
    CO_OFFICER = "CO_OFFICER", "Co-officer in organization"
    SOCIAL_CONNECTION = "SOCIAL_CONNECTION", "Social media connection"
    ATTORNEY_CLIENT = "ATTORNEY_CLIENT", "Attorney / Client"
    EMPLOYER_EMPLOYEE = "EMPLOYER_EMPLOYEE", "Employer / Employee"
    OTHER = "OTHER", "Other"


class RelationshipSource(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Extracted from document"
    SOS_FILING = "SOS_FILING", "Secretary of State filing"
    SOCIAL_MEDIA = "SOCIAL_MEDIA", "Social media (Facebook, etc.)"
    OBITUARY = "OBITUARY", "Obituary"
    PUBLIC_RECORD = "PUBLIC_RECORD", "Public record"
    INVESTIGATOR = "INVESTIGATOR", "Investigator observation"


class Relationship(UUIDPrimaryKeyModel):
    """
    Directional relationship between two persons.
    person_a → person_b with a typed connection.

    For symmetric relationships (SPOUSE, SIBLING), we store one row
    and the signal engine checks both directions.
    For asymmetric (PARENT_CHILD), person_a is the parent.
    """

    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="relationships")
    person_a = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="relationships_as_a"
    )
    person_b = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="relationships_as_b"
    )
    relationship_type = models.CharField(max_length=30, choices=RelationshipType.choices)
    source = models.CharField(
        max_length=20, choices=RelationshipSource.choices, default=RelationshipSource.INVESTIGATOR
    )
    source_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="relationship_evidence",
    )
    confidence = models.FloatField(
        default=1.0, help_text="0.0–1.0. Lower for inferred relationships."
    )
    notes = models.TextField(blank=True, default="")
    discovered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "relationships"
        constraints = [
            models.UniqueConstraint(
                fields=["person_a", "person_b", "relationship_type"],
                name="uniq_relationship_pair_type",
            ),
        ]
        indexes = [
            models.Index(fields=["case"], name="idx_relationships_case"),
            models.Index(fields=["relationship_type"], name="idx_relationships_type"),
        ]

    def __str__(self) -> str:
        return f"{self.person_a} → {self.person_b} ({self.relationship_type})"


# ──────────────────────────────────────────────────────────────────────
# NEW: TransactionChain — groups related property transactions to
# detect INSIDER SWAP patterns
# ──────────────────────────────────────────────────────────────────────
#
# WHY: The ExampleOwner insider swap works like this:
#   1. Charity buys property from ExampleOwner (charity = buyer)
#   2. Same property later transferred to ExampleOwner-connected entity
#      or charity sells below market to insider
#
# A single PropertyTransaction can't see this pattern — you need to
# GROUP related transactions into a chain and analyze the chain as a whole.
#
# The signal engine query:
#   chains = TransactionChain.objects.filter(
#       chain_type='INSIDER_SWAP', case=case
#   ).prefetch_related('links__transaction')
#   for chain in chains:
#       txns = [link.transaction for link in chain.links.all()]
#       # Check if buyer in txn[0] is related to seller in txn[1]
# ──────────────────────────────────────────────────────────────────────


class ChainType(models.TextChoices):
    INSIDER_SWAP = "INSIDER_SWAP", "Insider swap (buy → related-party transfer)"
    FLIP = "FLIP", "Property flip (buy → quick resale)"
    CIRCULAR = "CIRCULAR", "Circular transfer (A→B→C→A)"
    LAYERED = "LAYERED", "Layered transactions (obscuring beneficial owner)"
    OTHER = "OTHER", "Other pattern"


class ChainStatus(models.TextChoices):
    SUSPECTED = "SUSPECTED", "System-detected, awaiting review"
    CONFIRMED = "CONFIRMED", "Investigator-confirmed pattern"
    DISMISSED = "DISMISSED", "False positive"
    ESCALATED = "ESCALATED", "Escalated to finding"


class TransactionChain(UUIDPrimaryKeyModel):
    """
    Groups related PropertyTransactions into a detected pattern.

    Example: The "Insider insider swap" chain would contain:
      Link 1: Charity buys 5765 Burkettsville Rd (2021-06-28)
      Link 2: Insiders use property as charity-connected insiders
    The chain_type=INSIDER_SWAP and the signal engine can analyze the
    full sequence to compute time deltas, price differentials, and
    relationship connections between parties.
    """

    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="transaction_chains")
    chain_type = models.CharField(max_length=20, choices=ChainType.choices)
    status = models.CharField(
        max_length=20, choices=ChainStatus.choices, default=ChainStatus.SUSPECTED
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label, e.g. 'ExampleOwner → Example Charity swap (SR-068)'",
    )
    total_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Sum of all transaction prices in the chain.",
    )
    time_span_days = models.IntegerField(
        blank=True,
        null=True,
        help_text="Days between first and last transaction in chain.",
    )
    finding = models.ForeignKey(
        "Finding",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="transaction_chains",
        help_text="The Finding record that triggered creation of this chain.",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "transaction_chains"
        indexes = [
            models.Index(fields=["case"], name="idx_tx_chains_case"),
            models.Index(fields=["chain_type"], name="idx_tx_chains_type"),
            models.Index(fields=["status"], name="idx_tx_chains_status"),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.chain_type})"


class TransactionChainLink(UUIDPrimaryKeyModel):
    """
    One step in a TransactionChain. Links a PropertyTransaction to its
    position in the sequence (sequence_number).
    """

    chain = models.ForeignKey(TransactionChain, on_delete=models.CASCADE, related_name="links")
    transaction = models.ForeignKey(
        PropertyTransaction, on_delete=models.CASCADE, related_name="chain_links"
    )
    sequence_number = models.PositiveIntegerField(
        help_text="Order in chain: 1 = first transaction, 2 = second, etc."
    )
    role_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="E.g. 'Charity purchases from ExampleOwner' or 'Insider receives property'",
    )

    class Meta:
        db_table = "transaction_chain_links"
        constraints = [
            models.UniqueConstraint(fields=["chain", "transaction"], name="uniq_chain_transaction"),
            models.UniqueConstraint(
                fields=["chain", "sequence_number"], name="uniq_chain_sequence"
            ),
        ]
        ordering = ["sequence_number"]


class FinancialSnapshot(UUIDPrimaryKeyModel):
    """
    Financial data extracted from an IRS Form 990 filing.
    One row per document per tax year. Stores Part I summary, balance sheet,
    and governance indicators. Supports year-over-year trend analysis.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="financial_snapshots"
    )
    case = models.ForeignKey(Case, on_delete=models.RESTRICT, related_name="financial_snapshots")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_snapshots",
    )
    ein = models.CharField(max_length=20, blank=True, default="")
    tax_year = models.IntegerField()
    form_type = models.CharField(max_length=20, default="990")

    # Part I — Revenue
    total_contributions = models.BigIntegerField(null=True, blank=True)
    program_service_revenue = models.BigIntegerField(null=True, blank=True)
    investment_income = models.BigIntegerField(null=True, blank=True)
    other_revenue = models.BigIntegerField(null=True, blank=True)
    total_revenue = models.BigIntegerField(null=True, blank=True)

    # Part I — Expenses
    grants_paid = models.BigIntegerField(null=True, blank=True)
    salaries_and_compensation = models.BigIntegerField(null=True, blank=True)
    professional_fundraising = models.BigIntegerField(null=True, blank=True)
    other_expenses = models.BigIntegerField(null=True, blank=True)
    total_expenses = models.BigIntegerField(null=True, blank=True)

    # Part I — Bottom line
    revenue_less_expenses = models.BigIntegerField(null=True, blank=True)

    # Balance Sheet (Part X)
    total_assets_boy = models.BigIntegerField(null=True, blank=True)
    total_assets_eoy = models.BigIntegerField(null=True, blank=True)
    total_liabilities_boy = models.BigIntegerField(null=True, blank=True)
    total_liabilities_eoy = models.BigIntegerField(null=True, blank=True)
    net_assets_boy = models.BigIntegerField(null=True, blank=True)
    net_assets_eoy = models.BigIntegerField(null=True, blank=True)

    # Compensation (Part VII summary)
    officer_compensation_total = models.BigIntegerField(null=True, blank=True)
    num_employees = models.IntegerField(null=True, blank=True)
    num_voting_members = models.IntegerField(null=True, blank=True)
    num_independent_members = models.IntegerField(null=True, blank=True)

    # Source tracking
    source = models.CharField(
        max_length=20,
        default="EXTRACTED",
        help_text="EXTRACTED (from document OCR), PROPUBLICA (API), MANUAL",
    )
    confidence = models.FloatField(default=1.0, help_text="0.0–1.0 extraction confidence")
    raw_extraction = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "financial_snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "tax_year"],
                name="uniq_financial_snapshot_doc_year",
            ),
        ]
        indexes = [
            models.Index(fields=["case"], name="idx_fin_snapshot_case"),
            models.Index(fields=["tax_year"], name="idx_fin_snapshot_year"),
        ]
        ordering = ["-tax_year"]

    def __str__(self) -> str:
        return f"990 {self.tax_year} — {self.ein or 'no EIN'}"


class Finding(UUIDPrimaryKeyModel):
    """
    Consolidated finding model — replaces the old Signal → Detection → Finding
    three-table pipeline with a single table that has two dimensions:
      - status: where is this in the review process?
      - evidence_weight: how strong is the supporting evidence?

    Auto-generated findings start as NEW + SPECULATIVE. The investigator
    triages them by updating status and evidence_weight independently.
    """

    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="findings"
    )
    rule_id = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text=(
            "Signal rule that generated this (e.g. SR-003). "
            "Blank for manual findings."
        ),
    )
    title = models.CharField(max_length=500)
    description = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Machine-generated explanation of what triggered this finding."
        ),
    )
    narrative = models.TextField(
        blank=True,
        default="",
        help_text="Investigator-written narrative for the referral package.",
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=FindingStatus.choices,
        default=FindingStatus.NEW,
    )
    evidence_weight = models.CharField(
        max_length=20,
        choices=EvidenceWeight.choices,
        default=EvidenceWeight.SPECULATIVE,
    )
    source = models.CharField(
        max_length=20,
        choices=FindingSource.choices,
        default=FindingSource.AUTO,
    )
    investigator_note = models.TextField(
        blank=True,
        default="",
        help_text="Investigator notes — required when dismissing.",
    )
    legal_refs = ArrayField(
        models.CharField(max_length=200),
        blank=True,
        default=list,
        help_text="ORC sections and federal statutes (e.g. '18 U.S.C. § 1343').",
    )
    evidence_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured evidence data captured at detection time.",
    )
    trigger_doc = models.ForeignKey(
        "Document",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="findings_triggered",
    )
    trigger_entity_id = models.UUIDField(
        blank=True,
        null=True,
        help_text="UUID of the entity this finding is primarily about.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "findings"
        indexes = [
            models.Index(fields=["case"], name="idx_findings_case_id"),
            models.Index(fields=["rule_id"], name="idx_findings_rule_id"),
            models.Index(fields=["status"], name="idx_findings_status"),
            models.Index(
                fields=["case", "status"],
                name="idx_findings_case_status",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"{self.rule_id or 'MANUAL'} [{self.severity}] — {self.status}"
        )


class FindingEntity(UUIDPrimaryKeyModel):
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="entity_links"
    )
    entity_id = models.UUIDField()
    entity_type = models.CharField(max_length=50)
    context_note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "finding_entity"
        indexes = [
            models.Index(
                fields=["finding"], name="idx_finding_entity_finding"
            ),
        ]


class FindingDocument(UUIDPrimaryKeyModel):
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="document_links"
    )
    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="finding_links",
    )
    page_reference = models.CharField(
        max_length=100, blank=True, default=""
    )
    context_note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "finding_document"
        constraints = [
            models.UniqueConstraint(
                fields=["finding", "document"],
                name="uniq_finding_document_pair",
            ),
        ]
        indexes = [
            models.Index(
                fields=["document"],
                name="idx_finding_document_doc",
            ),
        ]


class AuditAction(models.TextChoices):
    """Constrained set of audit actions — prevents typos and enables filtering."""

    # Document lifecycle
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED", "Document ingested"
    DOCUMENT_SCRUBBED = "DOCUMENT_SCRUBBED", "Document metadata scrubbed"
    DOCUMENT_HASHED = "DOCUMENT_HASHED", "Document hash computed"
    DOCUMENT_HASH_VERIFIED = "DOCUMENT_HASH_VERIFIED", "Document hash re-verified"
    DOCUMENT_HASH_MISMATCH = "DOCUMENT_HASH_MISMATCH", "Document hash mismatch detected"
    DOCUMENT_DELETED = "DOCUMENT_DELETED", "Document deleted"
    DOCUMENT_OCR_COMPLETED = "DOCUMENT_OCR_COMPLETED", "Document OCR completed"
    DOCUMENT_OCR_FAILED = "DOCUMENT_OCR_FAILED", "Document OCR failed"

    # Record CRUD
    RECORD_CREATED = "RECORD_CREATED", "Record created"
    RECORD_UPDATED = "RECORD_UPDATED", "Record updated"
    RECORD_DELETED = "RECORD_DELETED", "Record deleted"

    # Signal / detection lifecycle
    SIGNAL_DETECTED = "SIGNAL_DETECTED", "Signal detected"
    SIGNAL_CONFIRMED = "SIGNAL_CONFIRMED", "Signal confirmed"
    SIGNAL_DISMISSED = "SIGNAL_DISMISSED", "Signal dismissed"
    SIGNAL_ESCALATED = "SIGNAL_ESCALATED", "Signal escalated to finding"

    # Finding lifecycle
    FINDING_CREATED = "FINDING_CREATED", "Finding created"
    FINDING_UPDATED = "FINDING_UPDATED", "Finding updated"
    FINDING_INCLUDED = "FINDING_INCLUDED", "Finding included in memo"

    # Referral lifecycle
    REFERRAL_CREATED = "REFERRAL_CREATED", "Referral created"
    REFERRAL_SUBMITTED = "REFERRAL_SUBMITTED", "Referral submitted"
    REFERRAL_STATUS_CHANGED = "REFERRAL_STATUS_CHANGED", "Referral status changed"

    # Intake validation
    INTAKE_REJECTED_SIZE = "INTAKE_REJECTED_SIZE", "File rejected — exceeds size limit"
    INTAKE_REJECTED_TYPE = "INTAKE_REJECTED_TYPE", "File rejected — invalid MIME type"
    INTAKE_REJECTED_CORRUPT = "INTAKE_REJECTED_CORRUPT", "File rejected — corrupted or unreadable"

    # System
    HASH_VERIFICATION_BATCH = "HASH_VERIFICATION_BATCH", "Batch hash verification completed"


class AuditLog(UUIDPrimaryKeyModel):
    """
    Append-only forensic audit log.

    SECURITY RULE: Application code MUST NOT issue DELETE or UPDATE
    statements against this table. This table is evidence of what happened.

    See SECURITY.md Rule 3: "Log Everything, Delete Nothing"
    """

    case_id = models.UUIDField(blank=True, null=True)
    table_name = models.CharField(max_length=100)
    record_id = models.UUIDField(blank=True, null=True)
    action = models.CharField(
        max_length=50,
        choices=AuditAction.choices,
        help_text="Constrained action type — use AuditAction enum values only.",
    )
    before_state = models.JSONField(blank=True, null=True)
    after_state = models.JSONField(blank=True, null=True)
    sha256_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 hash of the document involved, if applicable.",
    )
    file_size = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="File size in bytes at time of operation, if applicable.",
    )
    performed_by = models.CharField(max_length=255, blank=True, null=True)
    performed_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    success = models.BooleanField(
        default=True,
        help_text="False if the operation failed. Failure details go in notes.",
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["case_id"], name="idx_audit_log_case_id"),
            models.Index(fields=["performed_at"], name="idx_audit_log_performed_at"),
            models.Index(fields=["table_name", "record_id"], name="idx_audit_log_record"),
            models.Index(fields=["action"], name="idx_audit_log_action"),
        ]

    def __str__(self) -> str:
        status = "OK" if self.success else "FAILED"
        return f"[{self.performed_at:%Y-%m-%d %H:%M}] {self.action} ({status})"

    @classmethod
    def log(
        cls,
        *,
        action: str,
        table_name: str,
        record_id=None,
        case_id=None,
        before_state=None,
        after_state=None,
        sha256_hash: str = "",
        file_size: int | None = None,
        performed_by: str | None = None,
        ip_address: str | None = None,
        success: bool = True,
        notes: str | None = None,
    ) -> "AuditLog":
        """
        Convenience factory method for creating audit entries.

        Usage:
            AuditLog.log(
                action=AuditAction.DOCUMENT_INGESTED,
                table_name="documents",
                record_id=doc.id,
                case_id=doc.case_id,
                sha256_hash=computed_hash,
                file_size=uploaded_file.size,
                performed_by="tyler",
            )
        """
        return cls.objects.create(
            action=action,
            table_name=table_name,
            record_id=record_id,
            case_id=case_id,
            before_state=before_state,
            after_state=after_state,
            sha256_hash=sha256_hash,
            file_size=file_size,
            performed_by=performed_by,
            ip_address=ip_address,
            success=success,
            notes=notes,
        )


class InvestigatorNote(models.Model):
    """
    Free-form note attached to any entity in a case (case, document, finding,
    person, organization, property, financial instrument).

    Restored from migration 0013 — was missing from models.py due to truncation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey("Case", on_delete=models.CASCADE, related_name="investigator_notes")
    target_type = models.CharField(
        max_length=50,
        help_text=(
            "The type of entity this note is attached to: case, document, "
            "finding, person, organization, property, financial_instrument."
        ),
    )
    target_id = models.UUIDField(
        help_text="The primary key of the target record this note is attached to."
    )
    content = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "investigator_notes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["case"], name="idx_inv_notes_case"),
            models.Index(fields=["target_type", "target_id"], name="idx_inv_notes_target"),
        ]

    def __str__(self) -> str:
        return f"Note on {self.target_type} ({self.created_at:%Y-%m-%d})"


class JobType(models.TextChoices):
    IRS_NAME_SEARCH = "IRS_NAME_SEARCH", "IRS Name Search"
    IRS_FETCH_XML = "IRS_FETCH_XML", "IRS Fetch XML"
    OHIO_AOS = "OHIO_AOS", "Ohio Auditor of State"
    COUNTY_PARCEL = "COUNTY_PARCEL", "County Parcel Search"


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class SearchJob(UUIDPrimaryKeyModel):
    """Async research job — tracks state of a backgrounded external-data fetch.

    The four slow research endpoints (`/research/irs/` name search,
    `/research/irs/` with fetch_xml=true, `/research/ohio-aos/`,
    `/research/parcels/`) create a SearchJob row, enqueue a Django-Q2
    task, and return 202 with the job_id. A worker in the qcluster
    container picks the task up, calls the connector code, and writes
    the response payload to `result`. The frontend polls
    `/api/jobs/<id>/` for status + result.
    """

    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_jobs",
    )
    job_type = models.CharField(max_length=32, choices=JobType.choices)
    status = models.CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
    )
    query_params = models.JSONField()
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_jobs",
    )

    class Meta:
        indexes = [
            models.Index(fields=["case", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.job_type} {self.status} ({self.id})"
