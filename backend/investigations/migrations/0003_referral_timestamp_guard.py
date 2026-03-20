from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("investigations", "0002_governmentreferral"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE government_referrals
                SET filing_date = NOW()
                WHERE filing_date IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="governmentreferral",
            name="filing_date",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION prevent_government_referral_filing_date_update()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.filing_date IS DISTINCT FROM OLD.filing_date THEN
                        RAISE EXCEPTION 'filing_date is immutable after creation';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_prevent_referral_filing_date_update ON government_referrals;
                CREATE TRIGGER trg_prevent_referral_filing_date_update
                BEFORE UPDATE OF filing_date ON government_referrals
                FOR EACH ROW
                EXECUTE FUNCTION prevent_government_referral_filing_date_update();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS trg_prevent_referral_filing_date_update ON government_referrals;
                DROP FUNCTION IF EXISTS prevent_government_referral_filing_date_update();
            """,
        ),
    ]
