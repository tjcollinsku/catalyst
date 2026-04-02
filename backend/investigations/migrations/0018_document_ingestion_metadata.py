"""Add ingestion_metadata JSONField to Document model for chain-of-custody.

Captures PDF metadata (author, creator, producer, timestamps, page count,
encryption status, form detection) and upload context (original filename,
content type, size, SHA-256) at ingestion time. This field is never modified
after initial capture — it serves as a forensic provenance record.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investigations", "0017_document_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="ingestion_metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Chain-of-custody metadata captured at ingestion time. Includes: "
                    "PDF author, creator software, producer, creation/modification dates, "
                    "page count, encryption status, form detection. Stored as JSON for "
                    "flexibility across document types. Never modified after initial capture."
                ),
            ),
        ),
    ]
