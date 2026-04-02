"""Add display_name field to Document model for forensic canonical filenames.

The display_name follows the schema: YYYY-MM-DD_Entity_DocType.ext
Generated automatically by the upload pipeline after entity extraction.
The original filename is preserved in the 'filename' field for chain-of-custody.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investigations", "0016_auditlog_file_size_auditlog_sha256_hash_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="display_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Forensic canonical name: YYYY-MM-DD_Entity_DocType.ext. "
                    "Generated automatically by the pipeline. Original filename "
                    "preserved in 'filename' for chain-of-custody."
                ),
                max_length=255,
            ),
        ),
    ]
