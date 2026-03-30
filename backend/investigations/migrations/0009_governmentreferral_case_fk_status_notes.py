import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investigations", "0008_org_formation_date_signal_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="governmentreferral",
            name="case",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="referrals",
                to="investigations.case",
            ),
        ),
        migrations.AddField(
            model_name="governmentreferral",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="governmentreferral",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("ACKNOWLEDGED", "Acknowledged"),
                    ("CLOSED", "Closed"),
                ],
                db_default="DRAFT",
                default="DRAFT",
                max_length=50,
            ),
        ),
    ]
