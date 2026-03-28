import uuid

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Now
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
    OTHER = "OTHER", "Other"


class OcrStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    NOT_NEEDED = "NOT_NEEDED", "Not needed"


class OrganizationType(models.TextChoices):
    CHARITY = "CHARITY", "Charity"
    LLC = "LLC", "LLC"
    CORPORATION = "CORPORATION", "Corporation"
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
    CONTRACTOR = "CONTRACTOR", "Contractor"
    FAMILY_MEMBER = "FAMILY_MEMBER", "Family member"
    SUBJECT_OF_INVESTIGATION = "SUBJECT_OF_INVESTIGATION", "Subject of investigation"
    WITNESS = "WITNESS", "Witness"


class FindingSeverity(models.TextChoices):
    CRITICAL = "CRITICAL", "Critical"
    HIGH = "HIGH", "High"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"
    INFORMATIONAL = "INFORMATIONAL", "Informational"


class FindingConfidence(models.TextChoices):
    CONFIRMED = "CONFIRMED", "Confirmed"
    PROBABLE = "PROBABLE", "Probable"
    POSSIBLE = "POSSIBLE", "Possible"


class FindingStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REVIEWED = "REVIEWED", "Reviewed"
    INCLUDED_IN_MEMO = "INCLUDED_IN_MEMO", "Included in memo"
    EXCLUDED = "EXCLUDED", "Excluded"
    REFERRED = "REFERRED", "Referred"


class SignalSeverity(models.TextChoices):
    CRITICAL = "CRITICAL", "Critical"
    HIGH = "HIGH", "High"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"


class SignalStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CONFIRMED = "CONFIRMED", "Confirmed"
    DISMISSED = "DISMISSED", "Dismissed"
    ESCALATED = "ESCALATED", "Escalated"


class Case(UUIDPrimaryKeyModel):
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=CaseStatus.choices, default=CaseStatus.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    referral_ref = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "cases"

    def __str__(self) -> str:
        return self.name


class Document(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="documents")
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    sha256_hash = models.CharField(max_length=64)
    file_size = models.BigIntegerField()
    doc_type = models.CharField(
        max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER)
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
        max_length=20, choices=OcrStatus.choices, default=OcrStatus.PENDING)
    extracted_text = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "documents"
        indexes = [models.Index(fields=["case"], name="idx_documents_case_id")]


class Person(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="persons")
    full_name = models.CharField(max_length=255)
    aliases = ArrayField(models.TextField(), blank=True, default=list)
    role_tags = ArrayField(
        models.CharField(max_length=50, choices=PersonRole.choices),
        blank=True,
        default=list,
    )
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
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="organizations")
    name = models.CharField(max_length=255)
    org_type = models.CharField(
        max_length=20, choices=OrganizationType.choices, default=OrganizationType.OTHER)
    ein = models.CharField(max_length=20, blank=True, null=True)
    registration_state = models.CharField(max_length=2, blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=OrganizationStatus.choices, default=OrganizationStatus.UNKNOWN)
    formation_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date the entity was legally formed per Secretary of State records. Used for SR-002 signal detection.",
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "organizations"
        indexes = [models.Index(
            fields=["case"], name="idx_organizations_case_id")]

    def __str__(self) -> str:
        return self.name


class Property(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="properties")
    parcel_number = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    assessed_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True)
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True)
    valuation_delta = models.GeneratedField(
        expression=F("purchase_price") - F("assessed_value"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
        null=True,
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "properties"
        indexes = [models.Index(
            fields=["case"], name="idx_properties_case_id")]


class FinancialInstrument(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="financial_instruments")
    instrument_type = models.CharField(
        max_length=20, choices=InstrumentType.choices, default=InstrumentType.OTHER)
    filing_number = models.CharField(max_length=100, blank=True, null=True)
    filing_date = models.DateField(blank=True, null=True)
    signer = models.ForeignKey(Person, on_delete=models.SET_NULL,
                               blank=True, null=True, related_name="signed_instruments")
    secured_party_id = models.UUIDField(blank=True, null=True)
    debtor_id = models.UUIDField(blank=True, null=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True)
    anomaly_flags = ArrayField(models.TextField(), blank=True, default=list)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "financial_instruments"
        indexes = [
            models.Index(fields=["case"],
                         name="idx_fin_instr_case_id"),
            models.Index(fields=["signer"],
                         name="idx_fin_instr_signer"),
        ]


class PersonDocument(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent pair uniqueness.
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="person_links")
    page_reference = models.CharField(max_length=100, blank=True, null=True)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "person_document"
        constraints = [
            models.UniqueConstraint(
                fields=["person", "document"], name="uniq_person_document_pair"),
        ]
        indexes = [models.Index(fields=["document"],
                                name="idx_person_document_doc")]


class OrgDocument(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent pair uniqueness.
    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="org_links")
    page_reference = models.CharField(max_length=100, blank=True, null=True)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "org_document"
        constraints = [models.UniqueConstraint(
            fields=["org", "document"], name="uniq_org_document_pair")]
        indexes = [models.Index(fields=["document"],
                                name="idx_org_document_doc")]


class PersonOrganization(UUIDPrimaryKeyModel):
    # Django ORM currently does not support composite primary keys.
    # We keep a surrogate UUID PK and enforce SQL-equivalent tuple uniqueness.
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="organization_roles")
    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="person_roles")
    role = models.CharField(max_length=100)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "person_org"
        constraints = [
            models.UniqueConstraint(
                fields=["person", "org", "role"], name="uniq_person_org_role"),
        ]


class PropertyTransaction(UUIDPrimaryKeyModel):
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="transactions")
    document = models.ForeignKey(Document, on_delete=models.SET_NULL,
                                 blank=True, null=True, related_name="property_transactions")
    transaction_date = models.DateField(blank=True, null=True)
    buyer_id = models.UUIDField(blank=True, null=True)
    seller_id = models.UUIDField(blank=True, null=True)
    price = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "property_transaction"
        indexes = [models.Index(fields=["property"],
                                name="idx_prop_tx_property")]


class Signal(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="signals")
    rule_id = models.CharField(max_length=10)
    severity = models.CharField(
        max_length=20, choices=SignalSeverity.choices, default=SignalSeverity.MEDIUM)
    trigger_entity_id = models.UUIDField(blank=True, null=True)
    trigger_doc = models.ForeignKey(
        Document, on_delete=models.SET_NULL, blank=True, null=True, related_name="signals")
    status = models.CharField(
        max_length=20, choices=SignalStatus.choices, default=SignalStatus.OPEN)
    investigator_note = models.TextField(
        blank=True,
        null=True,
        help_text="Required when dismissed — rationale for dismissal.",
    )
    detected_summary = models.TextField(
        blank=True,
        default="",
        help_text="Machine-generated explanation of what triggered this signal.",
    )
    detected_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "signals"
        indexes = [
            models.Index(fields=["case"], name="idx_signals_case_id"),
            models.Index(fields=["rule_id"], name="idx_signals_rule_id"),
            models.Index(fields=["status"], name="idx_signals_status"),
        ]

    def __str__(self) -> str:
        return f"{self.rule_id} [{self.severity}] — {self.status}"


class Finding(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="findings")
    title = models.CharField(max_length=500)
    narrative = models.TextField()
    severity = models.CharField(
        max_length=20, choices=FindingSeverity.choices, default=FindingSeverity.MEDIUM)
    confidence = models.CharField(
        max_length=20, choices=FindingConfidence.choices, default=FindingConfidence.POSSIBLE)
    status = models.CharField(
        max_length=20, choices=FindingStatus.choices, default=FindingStatus.DRAFT)
    signal_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=(
            "Category of anomaly: VALUATION_ANOMALY, DATE_ANOMALY, "
            "DISCLOSURE_OMISSION, CONCENTRATION_FLAG, IDENTITY_FRAUD, etc."
        ),
    )
    signal_rule_id = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Originating signal rule (e.g. SR-001) if applicable.",
    )
    legal_refs = ArrayField(
        models.CharField(max_length=200),
        blank=True,
        default=list,
        help_text="ORC sections and federal statutes (e.g. '18 U.S.C. § 1343').",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "findings"
        indexes = [models.Index(fields=["case"], name="idx_findings_case_id")]


class FindingEntity(UUIDPrimaryKeyModel):
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="entity_links")
    entity_id = models.UUIDField()
    entity_type = models.CharField(max_length=50)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "finding_entity"
        indexes = [models.Index(
            fields=["finding"], name="idx_finding_entity_finding")]


class FindingDocument(UUIDPrimaryKeyModel):
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="finding_links")
    page_reference = models.CharField(max_length=100, blank=True, null=True)
    context_note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "finding_document"
        constraints = [
            models.UniqueConstraint(
                fields=["finding", "document"], name="uniq_finding_document_pair"),
        ]
        indexes = [models.Index(fields=["document"],
                                name="idx_finding_document_doc")]


class EntitySignal(UUIDPrimaryKeyModel):
    signal = models.ForeignKey(
        Signal, on_delete=models.CASCADE, related_name="entity_links")
    entity_id = models.UUIDField()
    entity_type = models.CharField(max_length=50)

    class Meta:
        db_table = "entity_signal"
        constraints = [
            models.UniqueConstraint(
                fields=["signal", "entity_id", "entity_type"], name="uniq_entity_signal"),
        ]
        indexes = [models.Index(
            fields=["signal"], name="idx_entity_signal_signal")]


class AuditLog(UUIDPrimaryKeyModel):
    case_id = models.UUIDField(blank=True, null=True)
    table_name = models.CharField(max_length=100)
    record_id = models.UUIDField(blank=True, null=True)
    action = models.CharField(max_length=50)
    before_state = models.JSONField(blank=True, null=True)
    after_state = models.JSONField(blank=True, null=True)
    performed_by = models.CharField(max_length=255, blank=True, null=True)
    performed_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["case_id"], name="idx_audit_log_case_id"),
            models.Index(fields=["performed_at"],
                         name="idx_audit_log_performed_at"),
            models.Index(fields=["table_name", "record_id"],
                         name="idx_audit_log_record"),
        ]


class GovernmentReferral(models.Model):
    referral_id = models.AutoField(primary_key=True)
    agency_name = models.CharField(max_length=100, blank=True, null=True)
    submission_id = models.CharField(max_length=255, blank=True, null=True)
    filing_date = models.DateTimeField(default=timezone.now, db_default=Now())
    contact_alias = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(
        max_length=50, default="Submitted", db_default=Value("Submitted"))

    class Meta:
        db_table = "government_referrals"

    def save(self, *args, **kwargs):
        if self.pk:
            original = GovernmentReferral.objects.filter(pk=self.pk).values_list(
                "filing_date", flat=True
            ).first()
            if original is not None and self.filing_date != original:
                raise ValidationError(
                    "filing_date is immutable after creation.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.agency_name or 'Unknown Agency'} ({self.status})"
