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
    UCC = "UCC", "UCC"
    IRS_990 = "IRS_990", "IRS 990"
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
        max_length=20, choices=DocumentType.choices, default=DocumentType.OTHER)
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
    role_tags = ArrayField(models.TextField(), blank=True, default=list)
    date_of_death = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "persons"
        indexes = [models.Index(fields=["case"], name="idx_persons_case_id")]

    def __str__(self) -> str:
        return self.full_name


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


class Finding(UUIDPrimaryKeyModel):
    case = models.ForeignKey(
        Case, on_delete=models.RESTRICT, related_name="findings")
    title = models.CharField(max_length=500)
    narrative = models.TextField()
    orc_reference = models.CharField(max_length=100, blank=True, null=True)
    severity = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "findings"
        indexes = [models.Index(fields=["case"], name="idx_findings_case_id")]


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
