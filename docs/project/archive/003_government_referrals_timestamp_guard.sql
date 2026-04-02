-- =============================================================================
-- Catalyst Intelligence Triage Platform
-- Migration 003: government_referrals filing_date guard
-- =============================================================================

-- Backfill any existing null filing timestamps before hardening constraints.
UPDATE government_referrals
SET filing_date = NOW()
WHERE filing_date IS NULL;

-- Auto-set filing timestamp on insert when not provided.
ALTER TABLE government_referrals
ALTER COLUMN filing_date SET DEFAULT NOW();

-- Require a filing timestamp for every referral row.
ALTER TABLE government_referrals
ALTER COLUMN filing_date SET NOT NULL;

-- Prevent filing_date edits after insert.
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
