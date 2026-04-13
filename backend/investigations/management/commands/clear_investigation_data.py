"""
Management command: clear_investigation_data

Deletes all Catalyst investigation data from the database while preserving
Django system tables (users, sessions, migrations, permissions).

Usage:
    python manage.py clear_investigation_data --confirm

The --confirm flag is required to prevent accidental runs.
"""

from django.core.management.base import BaseCommand

from investigations.models import (
    Address,
    AuditLog,
    Case,
    Document,
    Finding,
    FindingDocument,
    FindingEntity,
    FinancialInstrument,
    FinancialSnapshot,
    InvestigatorNote,
    OrgAddress,
    OrgDocument,
    Organization,
    Person,
    PersonAddress,
    PersonDocument,
    PersonOrganization,
    Property,
    PropertyTransaction,
    Relationship,
    TransactionChain,
    TransactionChainLink,
)


class Command(BaseCommand):
    """
    Django management commands always follow this pattern:
      - A class named Command that inherits from BaseCommand
      - A help string describing what the command does
      - An add_arguments() method for any flags/options
      - A handle() method that contains the actual logic
    """

    help = "Clears all Catalyst investigation data. Preserves Django users and system tables."

    def add_arguments(self, parser):
        """
        add_arguments() lets us define command-line flags.
        Here we require --confirm so nobody runs this by accident.
        'action="store_true"' means the flag is a boolean — present = True, absent = False.
        """
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required flag. You must pass --confirm to actually delete data.",
        )

    def handle(self, *args, **options):
        """
        handle() is the entry point — Django calls this when you run the command.
        *args and **options capture the command-line arguments we defined above.
        options["confirm"] will be True if the user passed --confirm, False otherwise.
        """

        # Safety check — refuse to run without the --confirm flag
        if not options["confirm"]:
            self.stdout.write(
                self.style.ERROR(
                    "Aborted. You must pass --confirm to delete data.\n"
                    "Run: python manage.py clear_investigation_data --confirm"
                )
            )
            return

        self.stdout.write(self.style.WARNING("Starting data clear..."))

        # ----------------------------------------------------------------
        # Count rows before deletion so we can report what was removed.
        # This also helps confirm the database isn't already empty.
        # ----------------------------------------------------------------
        counts_before = {
            "Cases": Case.objects.count(),
            "Documents": Document.objects.count(),
            "Persons": Person.objects.count(),
            "Organizations": Organization.objects.count(),
            "Properties": Property.objects.count(),
            "Findings": Finding.objects.count(),
            "FinancialSnapshots": FinancialSnapshot.objects.count(),
            "AuditLogs": AuditLog.objects.count(),
        }

        self.stdout.write("Rows found before deletion:")
        for label, count in counts_before.items():
            self.stdout.write(f"  {label}: {count}")

        # ----------------------------------------------------------------
        # Delete in dependency order (children before parents).
        #
        # Why does order matter?
        # PostgreSQL enforces "foreign key constraints" — if model B has a
        # FK pointing to model A, you can't delete an A row while B rows
        # still reference it. You'd get an IntegrityError.
        #
        # We delete the most "child-like" tables first and work up to Case,
        # which is the root that most things hang off.
        #
        # Note: Django's on_delete=CASCADE means if you delete a parent,
        # the child rows auto-delete too. But we're explicit here so the
        # log output shows exactly what happened.
        # ----------------------------------------------------------------

        # --- Junction / link tables (no children of their own) ---
        FindingDocument.objects.all().delete()
        self.stdout.write("  Deleted FindingDocuments")

        FindingEntity.objects.all().delete()
        self.stdout.write("  Deleted FindingEntities")

        TransactionChainLink.objects.all().delete()
        self.stdout.write("  Deleted TransactionChainLinks")

        PersonDocument.objects.all().delete()
        self.stdout.write("  Deleted PersonDocuments")

        OrgDocument.objects.all().delete()
        self.stdout.write("  Deleted OrgDocuments")

        PersonOrganization.objects.all().delete()
        self.stdout.write("  Deleted PersonOrganizations")

        PersonAddress.objects.all().delete()
        self.stdout.write("  Deleted PersonAddresses")

        OrgAddress.objects.all().delete()
        self.stdout.write("  Deleted OrgAddresses")

        # --- Mid-level models ---
        Finding.objects.all().delete()
        self.stdout.write("  Deleted Findings")

        Relationship.objects.all().delete()
        self.stdout.write("  Deleted Relationships")

        PropertyTransaction.objects.all().delete()
        self.stdout.write("  Deleted PropertyTransactions")

        TransactionChain.objects.all().delete()
        self.stdout.write("  Deleted TransactionChains")

        FinancialSnapshot.objects.all().delete()
        self.stdout.write("  Deleted FinancialSnapshots")

        FinancialInstrument.objects.all().delete()
        self.stdout.write("  Deleted FinancialInstruments")

        InvestigatorNote.objects.all().delete()
        self.stdout.write("  Deleted InvestigatorNotes")

        AuditLog.objects.all().delete()
        self.stdout.write("  Deleted AuditLogs")

        # --- Entity models ---
        Address.objects.all().delete()
        self.stdout.write("  Deleted Addresses")

        Property.objects.all().delete()
        self.stdout.write("  Deleted Properties")

        Organization.objects.all().delete()
        self.stdout.write("  Deleted Organizations")

        Person.objects.all().delete()
        self.stdout.write("  Deleted Persons")

        # --- Documents and Cases last (everything hangs off these) ---
        Document.objects.all().delete()
        self.stdout.write("  Deleted Documents")

        Case.objects.all().delete()
        self.stdout.write("  Deleted Cases")

        # ----------------------------------------------------------------
        # Final confirmation — show that the database is now empty
        # ----------------------------------------------------------------
        self.stdout.write(
            self.style.SUCCESS(
                "\nDone. All investigation data cleared. "
                "Django users and system tables were not touched.\n"
                "You can now run: python manage.py seed_demo"
            )
        )
