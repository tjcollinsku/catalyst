-- ============================================================================
-- Migration 004: Sync Database Schema with Django Models
-- ============================================================================
--
-- Purpose:
--   Bring PostgreSQL schema in sync with current Django models by:
--   1. Creating 4 missing tables (signals, finding_entity, finding_document, entity_signal)
--   2. Expanding doc_type ENUM with 13 new document types
--   3. Adding missing columns to existing tables
--   4. Adding new ENUMs for finding/signal enumerations
--
-- Status: Production-ready, idempotent for re-application
-- Applied: 2026-03-28
-- ============================================================================

-- ============================================================================
-- Step 1: Expand doc_type ENUM to include all 18 Django DocumentType choices
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_type') THEN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'PARCEL_RECORD'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'PARCEL_RECORD';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'RECORDER_INSTRUMENT'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'RECORDER_INSTRUMENT';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'MORTGAGE'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'MORTGAGE';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'LIEN'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'LIEN';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'IRS_990T'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'IRS_990T';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'BUILDING_PERMIT'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'BUILDING_PERMIT';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'CORP_FILING'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'CORP_FILING';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'SOS_FILING'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'SOS_FILING';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'COURT_FILING'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'COURT_FILING';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'DEATH_RECORD'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'DEATH_RECORD';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'SUSPECTED_FORGERY'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'SUSPECTED_FORGERY';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'WEB_ARCHIVE'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'WEB_ARCHIVE';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'doc_type' AND e.enumlabel = 'REFERRAL_MEMO'
        ) THEN
            ALTER TYPE doc_type ADD VALUE 'REFERRAL_MEMO';
        END IF;
    END IF;
END
$$;

-- ============================================================================
-- Step 2: Create new ENUMs for Finding and Signal statuses/severities
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'finding_severity') THEN
        CREATE TYPE finding_severity AS ENUM (
            'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'finding_confidence') THEN
        CREATE TYPE finding_confidence AS ENUM (
            'CONFIRMED', 'PROBABLE', 'POSSIBLE'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'finding_status') THEN
        CREATE TYPE finding_status AS ENUM (
            'DRAFT', 'REVIEWED', 'INCLUDED_IN_MEMO', 'EXCLUDED', 'REFERRED'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'signal_severity') THEN
        CREATE TYPE signal_severity AS ENUM (
            'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'signal_status') THEN
        CREATE TYPE signal_status AS ENUM (
            'OPEN', 'CONFIRMED', 'DISMISSED', 'ESCALATED'
        );
    END IF;
END
$$;

-- ============================================================================
-- Step 3: Add missing columns to documents table
-- ============================================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS is_generated BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS doc_subtype VARCHAR(100) NOT NULL DEFAULT '';

COMMENT ON COLUMN documents.is_generated IS
    'True for outputs produced by Catalyst (memos, reports). False for source documents ingested as evidence.';
COMMENT ON COLUMN documents.doc_subtype IS
    'Optional free-text subtype for additional classification detail.';

-- ============================================================================
-- Step 4: Add missing columns to organizations table
-- ============================================================================

ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS formation_date DATE;

COMMENT ON COLUMN organizations.formation_date IS
    'Date the entity was legally formed per Secretary of State records. Used for SR-002 signal detection.';

-- ============================================================================
-- Step 5: Update findings table with missing columns
-- ============================================================================

ALTER TABLE findings
ADD COLUMN IF NOT EXISTS confidence finding_confidence NOT NULL DEFAULT 'POSSIBLE',
ADD COLUMN IF NOT EXISTS status finding_status NOT NULL DEFAULT 'DRAFT',
ADD COLUMN IF NOT EXISTS signal_type VARCHAR(50) NOT NULL DEFAULT '',
ADD COLUMN IF NOT EXISTS signal_rule_id VARCHAR(10) NOT NULL DEFAULT '',
ADD COLUMN IF NOT EXISTS legal_refs TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN findings.confidence IS 'Level of certainty in the finding.';
COMMENT ON COLUMN findings.status IS 'Workflow status of the finding.';
COMMENT ON COLUMN findings.signal_type IS
    'Category of anomaly: VALUATION_ANOMALY, DATE_ANOMALY, DISCLOSURE_OMISSION, CONCENTRATION_FLAG, IDENTITY_FRAUD, etc.';
COMMENT ON COLUMN findings.signal_rule_id IS
    'Originating signal rule (e.g. SR-001) if applicable.';
COMMENT ON COLUMN findings.legal_refs IS
    'ORC sections and federal statutes (e.g. ''18 U.S.C. Sec. 1343'').';

-- ============================================================================
-- Step 6: Create signals table
-- ============================================================================

CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    rule_id VARCHAR(10) NOT NULL,
    severity signal_severity NOT NULL DEFAULT 'MEDIUM',
    trigger_entity_id UUID,
    trigger_doc_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    status signal_status NOT NULL DEFAULT 'OPEN',
    investigator_note TEXT,
    detected_summary TEXT NOT NULL DEFAULT '',
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_case_id ON signals(case_id);
CREATE INDEX IF NOT EXISTS idx_signals_rule_id ON signals(rule_id);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_detected_at ON signals(detected_at DESC);

COMMENT ON TABLE signals IS
    'ML/rule-based anomaly detection results. Trigger workflow for human investigation.';
COMMENT ON COLUMN signals.investigator_note IS
    'Required when dismissed - rationale for dismissal.';
COMMENT ON COLUMN signals.detected_summary IS
    'Machine-generated explanation of what triggered this signal.';

-- ============================================================================
-- Step 7: Create finding_entity junction table
-- ============================================================================

CREATE TABLE IF NOT EXISTS finding_entity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    context_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finding_entity_finding ON finding_entity(finding_id);
CREATE INDEX IF NOT EXISTS idx_finding_entity_entity ON finding_entity(entity_id, entity_type);

COMMENT ON TABLE finding_entity IS
    'Junction: Links findings to persons, organizations, properties that support it.';

-- ============================================================================
-- Step 8: Create finding_document junction table
-- ============================================================================

CREATE TABLE IF NOT EXISTS finding_document (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_reference VARCHAR(100),
    context_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uniq_finding_document_pair'
          AND conrelid = 'finding_document'::regclass
    ) THEN
        ALTER TABLE finding_document
        ADD CONSTRAINT uniq_finding_document_pair UNIQUE (finding_id, document_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_finding_document_finding ON finding_document(finding_id);
CREATE INDEX IF NOT EXISTS idx_finding_document_document ON finding_document(document_id);

COMMENT ON TABLE finding_document IS
    'Junction: Links findings to source documents that support them.';

-- ============================================================================
-- Step 9: Create entity_signal junction table
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity_signal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uniq_entity_signal'
          AND conrelid = 'entity_signal'::regclass
    ) THEN
        ALTER TABLE entity_signal
        ADD CONSTRAINT uniq_entity_signal UNIQUE (signal_id, entity_id, entity_type);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_entity_signal_signal ON entity_signal(signal_id);
CREATE INDEX IF NOT EXISTS idx_entity_signal_entity ON entity_signal(entity_id, entity_type);

COMMENT ON TABLE entity_signal IS
    'Junction: Links signals to persons, organizations, properties mentioned in detection.';

-- ============================================================================
-- Step 10: Ensure signals timestamp trigger exists
-- ============================================================================

CREATE OR REPLACE FUNCTION update_signals_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'signals_update_timestamp'
          AND tgrelid = 'signals'::regclass
    ) THEN
        CREATE TRIGGER signals_update_timestamp
        BEFORE UPDATE ON signals
        FOR EACH ROW
        EXECUTE FUNCTION update_signals_timestamp();
    END IF;
END
$$;

-- ============================================================================
-- Step 11: Add search/performance indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_findings_signal_type
ON findings(signal_type)
WHERE signal_type != '';

CREATE INDEX IF NOT EXISTS idx_findings_signal_rule_id
ON findings(signal_rule_id)
WHERE signal_rule_id != '';

CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);

-- ============================================================================
-- Verification query
-- ============================================================================
-- SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
