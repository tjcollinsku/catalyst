from django.contrib import admin

from .models import (
    AuditLog,
    Case,
    Detection,
    Document,
    FinancialInstrument,
    Finding,
    GovernmentReferral,
    Organization,
    OrgDocument,
    Person,
    PersonDocument,
    PersonOrganization,
    Property,
    PropertyTransaction,
)


@admin.register(GovernmentReferral)
class GovernmentReferralAdmin(admin.ModelAdmin):
    list_display = (
        "referral_id",
        "case",
        "agency_name",
        "submission_id",
        "contact_alias",
        "status",
        "filing_date",
    )
    list_filter = ("status", "agency_name")
    search_fields = ("agency_name", "submission_id", "contact_alias")
    readonly_fields = ("filing_date",)
    ordering = ("-filing_date",)
    autocomplete_fields = ("case",)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at", "referral_ref")
    list_filter = ("status",)
    search_fields = ("name", "referral_ref")
    ordering = ("-created_at",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("filename", "case", "doc_type", "ocr_status", "uploaded_at")
    list_filter = ("doc_type", "ocr_status")
    search_fields = ("filename", "sha256_hash")
    ordering = ("-uploaded_at",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("full_name", "case", "date_of_death")
    search_fields = ("full_name",)
    list_filter = ("case",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "org_type", "status", "ein", "registration_state")
    list_filter = ("org_type", "status")
    search_fields = ("name", "ein")


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "severity", "confidence", "status", "created_at")
    list_filter = ("severity", "confidence", "status")
    search_fields = ("title", "narrative", "signal_type", "signal_rule_id")
    ordering = ("-created_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("table_name", "action", "performed_by", "performed_at", "record_id")
    list_filter = ("action", "table_name")
    search_fields = ("performed_by", "table_name")
    readonly_fields = (
        "case_id",
        "table_name",
        "record_id",
        "action",
        "before_state",
        "after_state",
        "performed_by",
        "performed_at",
        "ip_address",
        "notes",
    )
    ordering = ("-performed_at",)

    def has_add_permission(self, request):
        return False  # append-only — no manual inserts via admin

    def has_change_permission(self, request, obj=None):
        return False  # immutable — no edits via admin

    def has_delete_permission(self, request, obj=None):
        return False  # append-only — no deletes via admin


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "address",
        "parcel_number",
        "county",
        "assessed_value",
        "purchase_price",
        "case",
    )
    list_filter = ("county",)
    search_fields = ("address", "parcel_number", "county")
    ordering = ("county", "address")


@admin.register(FinancialInstrument)
class FinancialInstrumentAdmin(admin.ModelAdmin):
    list_display = ("filing_number", "instrument_type", "filing_date", "amount", "signer", "case")
    list_filter = ("instrument_type",)
    search_fields = ("filing_number",)
    ordering = ("-filing_date",)


@admin.register(PersonDocument)
class PersonDocumentAdmin(admin.ModelAdmin):
    list_display = ("person", "document", "page_reference")
    search_fields = ("person__full_name", "document__filename")
    ordering = ("person",)


@admin.register(OrgDocument)
class OrgDocumentAdmin(admin.ModelAdmin):
    list_display = ("org", "document", "page_reference")
    search_fields = ("org__name", "document__filename")
    ordering = ("org",)


@admin.register(PersonOrganization)
class PersonOrganizationAdmin(admin.ModelAdmin):
    list_display = ("person", "org", "role", "start_date", "end_date")
    list_filter = ("role",)
    search_fields = ("person__full_name", "org__name", "role")
    ordering = ("person",)


@admin.register(PropertyTransaction)
class PropertyTransactionAdmin(admin.ModelAdmin):
    list_display = ("property", "transaction_date", "price", "document")
    list_filter = ("transaction_date",)
    search_fields = ("property__address", "property__parcel_number")
    ordering = ("-transaction_date",)


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = ("signal_type", "severity", "status", "case", "detected_at")
    list_filter = ("signal_type", "severity", "status", "detection_method")
    search_fields = ("case__name", "investigator_note")
    ordering = ("-detected_at",)
    readonly_fields = ("detected_at",)
