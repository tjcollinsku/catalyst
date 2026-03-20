from django.contrib import admin

from .models import (
    AuditLog,
    Case,
    Document,
    Finding,
    FinancialInstrument,
    GovernmentReferral,
    OrgDocument,
    Organization,
    Person,
    PersonDocument,
    PersonOrganization,
    Property,
    PropertyTransaction,
)


@admin.register(GovernmentReferral)
class GovernmentReferralAdmin(admin.ModelAdmin):
    list_display = ("referral_id", "agency_name", "submission_id",
                    "contact_alias", "status", "filing_date")
    list_filter = ("status", "agency_name")
    search_fields = ("agency_name", "submission_id", "contact_alias")
    # immutable after creation — enforced here and in DB
    readonly_fields = ("filing_date",)
    ordering = ("-filing_date",)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at", "referral_ref")
    list_filter = ("status",)
    search_fields = ("name", "referral_ref")
    ordering = ("-created_at",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("filename", "case", "doc_type",
                    "ocr_status", "uploaded_at")
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
    list_display = ("title", "case", "severity", "orc_reference", "created_at")
    list_filter = ("severity",)
    search_fields = ("title", "orc_reference", "narrative")
    ordering = ("-created_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("table_name", "action", "performed_by",
                    "performed_at", "record_id")
    list_filter = ("action", "table_name")
    search_fields = ("performed_by", "table_name")
    readonly_fields = ("case_id", "table_name", "record_id", "action",
                       "before_state", "after_state", "performed_by",
                       "performed_at", "ip_address", "notes")
    ordering = ("-performed_at",)

    def has_add_permission(self, request):
        return False  # append-only — no manual inserts via admin

    def has_change_permission(self, request, obj=None):
        return False  # immutable — no edits via admin

    def has_delete_permission(self, request, obj=None):
        return False  # append-only — no deletes via admin


admin.site.register(Property)
admin.site.register(FinancialInstrument)
admin.site.register(PersonDocument)
admin.site.register(OrgDocument)
admin.site.register(PersonOrganization)
admin.site.register(PropertyTransaction)
