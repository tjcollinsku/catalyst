-- =============================================================================
-- Catalyst Intelligence Triage Platform
-- Migration 002: government_referrals
-- =============================================================================

CREATE TABLE IF NOT EXISTS government_referrals (
    referral_id SERIAL PRIMARY KEY,
    agency_name VARCHAR(100),
    submission_id VARCHAR(255),
    filing_date TIMESTAMP,
    contact_alias VARCHAR(100),
    status VARCHAR(50) DEFAULT 'Submitted'
);
