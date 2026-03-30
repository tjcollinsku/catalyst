from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investigations", "0009_governmentreferral_case_fk_status_notes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("DEED", "Deed"),
                    ("PARCEL_RECORD", "Parcel Record"),
                    ("RECORDER_INSTRUMENT", "Recorder Instrument"),
                    ("MORTGAGE", "Mortgage"),
                    ("LIEN", "Lien"),
                    ("UCC", "UCC Filing"),
                    ("IRS_990", "IRS Form 990"),
                    ("IRS_990T", "IRS Form 990-T"),
                    ("BUILDING_PERMIT", "Building Permit"),
                    ("CORP_FILING", "Corporate Filing"),
                    ("SOS_FILING", "SOS Filing"),
                    ("COURT_FILING", "Court Filing"),
                    ("DEATH_RECORD", "Death Record / Obituary"),
                    ("SUSPECTED_FORGERY", "Suspected Forgery"),
                    ("WEB_ARCHIVE", "Web Archive / Screenshot"),
                    ("REFERRAL_MEMO", "Referral / Complaint Memo"),
                    ("AUDITOR", "Auditor"),
                    ("OCC_REPORT", "OCC Report"),
                    ("CIC_REPORT", "CIC Report"),
                    ("OTHER", "Other"),
                ],
                default="OTHER",
                max_length=30,
            ),
        ),
    ]
