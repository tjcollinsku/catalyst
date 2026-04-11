"""
Management command: dedup_documents

Removes duplicate Document records caused by uploading the same file more than
once to the same case.  For each (case, filename) pair, the earliest upload is
kept and any later duplicates are deleted.  After cleanup the command re-runs
the signal detection pipeline against every kept document so that Detection
rows reflect the clean document set.

Usage
-----
    python manage.py dedup_documents
    python manage.py dedup_documents --dry-run
    python manage.py dedup_documents --case <uuid>
"""

from itertools import groupby

from django.core.management.base import BaseCommand

from investigations.models import Case, Document, Finding
from investigations.signal_rules import evaluate_case, evaluate_document, persist_signals


class Command(BaseCommand):
    help = "Remove duplicate Document rows and backfill Detection rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without making changes.",
        )
        parser.add_argument(
            "--case",
            metavar="UUID",
            help="Limit to a single case UUID.",
        )
        parser.add_argument(
            "--backfill",
            action="store_true",
            default=True,
            help="Re-run detection pipeline after dedup (default: True).",
        )
        parser.add_argument(
            "--no-backfill",
            dest="backfill",
            action="store_false",
            help="Skip the detection backfill step.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        backfill = options["backfill"]
        case_uuid = options["case"]

        if case_uuid:
            cases = Case.objects.filter(pk=case_uuid)
            if not cases.exists():
                self.stderr.write(f"No case found with id {case_uuid}")
                return
        else:
            cases = Case.objects.all()

        total_deleted = 0

        for case in cases:
            docs = list(Document.objects.filter(case=case).order_by("filename", "uploaded_at"))
            to_delete_ids = []

            for _filename, group in groupby(docs, key=lambda d: d.filename):
                items = list(group)
                if len(items) > 1:
                    # keep items[0] (earliest upload_at), delete the rest
                    dupes = items[1:]
                    for d in dupes:
                        self.stdout.write(
                            f"  {'[dry-run] ' if dry_run else ''}DELETE {d.filename} "
                            f"(id={d.pk}, uploaded={d.uploaded_at})"
                        )
                    to_delete_ids.extend(d.pk for d in dupes)

            if to_delete_ids and not dry_run:
                deleted, _ = Document.objects.filter(pk__in=to_delete_ids).delete()
                total_deleted += deleted
                self.stdout.write(
                    self.style.WARNING(f"Case {case.pk}: deleted {deleted} duplicate document(s).")
                )
            elif to_delete_ids and dry_run:
                self.stdout.write(
                    f"Case {case.pk}: would delete {len(to_delete_ids)} duplicate(s)."
                )
            else:
                self.stdout.write(f"Case {case.pk}: no duplicates found.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete — no changes made."))
            return

        self.stdout.write(self.style.SUCCESS(f"Dedup complete. Total deleted: {total_deleted}"))

        if not backfill:
            return

        self.stdout.write("Backfilling Finding rows from clean document set...")
        backfill_count = 0

        for case in cases:
            # Clear existing auto-generated findings so we start fresh
            cleared, _ = Finding.objects.filter(
                case=case, source="AUTO"
            ).delete()
            if cleared:
                self.stdout.write(
                    f"  Case {case.pk}: cleared {cleared} auto-findings."
                )

            docs = Document.objects.filter(case=case)
            for doc in docs:
                triggers = (
                    evaluate_document(case, doc)
                    + evaluate_case(case, trigger_doc=doc)
                )
                created = persist_signals(case, triggers)
                backfill_count += len(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. Created {backfill_count} finding(s)."
            )
        )
