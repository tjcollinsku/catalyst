# Generated for AI pattern augmentation — choice-only schema change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('investigations', '0022_searchjob'),
    ]

    operations = [
        migrations.AlterField(
            model_name='finding',
            name='source',
            field=models.CharField(
                choices=[
                    ('AUTO', 'Auto-detected by signal rules'),
                    ('MANUAL', 'Manually created by investigator'),
                    ('AI', 'AI-flagged pattern'),
                ],
                default='AUTO',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='searchjob',
            name='job_type',
            field=models.CharField(
                choices=[
                    ('IRS_NAME_SEARCH', 'IRS Name Search'),
                    ('IRS_FETCH_XML', 'IRS Fetch XML'),
                    ('OHIO_AOS', 'Ohio Auditor of State'),
                    ('COUNTY_PARCEL', 'County Parcel Search'),
                    ('AI_PATTERN_ANALYSIS', 'AI Pattern Analysis'),
                ],
                max_length=32,
            ),
        ),
    ]
