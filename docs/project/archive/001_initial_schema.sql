-- =============================================================================
-- Catalyst Intelligence Triage Platform
-- Migration 001: Initial Schema
-- Phase 1 — Foundation
-- =============================================================================
-- Run order matters. Tables with foreign keys must be created AFTER the tables
-- they reference. The order here: cases → documents → entities → junction tables


-- Enable the pgcrypto extension so we can use gen_random_uuid()
-- This gives every row a UUID primary key — a long random ID that is globally
-- unique. We use UUIDs instead of simple integers (1, 2, 3...) because UUIDs
-- don't leak information about how many records exist.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================================
-- CUSTOM TYPES (enumerations)
-- An ENUM is a column that can only hold one of a fixed list of values.
-- PostgreSQL enforces this at the database level — you can't accidentally
-- insert a typo like "ACTIV" instead of "ACTIVE".
-- =============================================================================

CREATE TYPE case_status AS ENUM (
    'ACTIVE',
    'PAUSED',
    'REFERRED',
    'CLOSED'
);

CREATE TYPE doc_type AS ENUM (
    'DEED',
    'UCC',
    'IRS_990',
    'AUDITOR',
    'OTHER'
);

CREATE TYPE ocr_status AS ENUM (
    'PENDING',
    'COMPLETED',
    'FAILED',
    'NOT_NEEDED'
);

CREATE TYPE org_type AS ENUM (
    'CHARITY',
    'LLC',
    'CORPORATION',
    'GOVERNMENT',
    'CIC',
    'OTHER'
);

CREATE TYPE org_status AS ENUM (
    'ACTIVE',
    'DISSOLVED',
    'REVOKED',
    'UNKNOWN'
);

CREATE TYPE instrument_type AS ENUM (
    'UCC_FILING',
    'LIEN',
    'MORTGAGE',
    'LOAN',
    'OTHER'
);


-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- cases
-- The top-level container. Every piece of data in the system belongs to a case.
-- Think of this as the "investigation folder."
-- -----------------------------------------------------------------------------
CREATE TABLE cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    status          case_status NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    notes           TEXT,
    referral_ref    VARCHAR(100)    -- e.g. "AG Ref #REDACTED" if referred to authorities
);

-- Add a comment directly in the database (shows up in psql \d+ cases)
COMMENT ON TABLE cases IS 'Top-level investigation container. All entities and documents belong to a case.';
COMMENT ON COLUMN cases.referral_ref IS 'External reference ID if case was referred to a government authority.';


-- -----------------------------------------------------------------------------
-- documents
-- Every source file uploaded to the system. The SHA-256 hash is computed at
-- intake and stored here — it proves the file has not been altered since upload.
-- -----------------------------------------------------------------------------
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    filename        VARCHAR(255) NOT NULL,
    file_path       VARCHAR(500) NOT NULL,      -- path inside MinIO file store
    sha256_hash     CHAR(64) NOT NULL,          -- exactly 64 hex characters
    file_size       BIGINT NOT NULL,            -- bytes
    doc_type        doc_type NOT NULL DEFAULT 'OTHER',
    source_url      VARCHAR(500),               -- where the file was downloaded from
    uploaded_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ocr_status      ocr_status NOT NULL DEFAULT 'PENDING',
    extracted_text  TEXT                        -- populated after processing
);

COMMENT ON TABLE documents IS 'Source files. Original files are immutable after intake. sha256_hash proves integrity.';
COMMENT ON COLUMN documents.sha256_hash IS 'SHA-256 hex digest computed at upload time. 64 characters, never NULL.';
COMMENT ON COLUMN documents.file_path IS 'Object path inside MinIO store. Never a local filesystem path.';

-- Index: we will often query "all documents for a case"
CREATE INDEX idx_documents_case_id ON documents(case_id);


-- =============================================================================
-- ENTITY TABLES
-- These five tables represent the real-world things that appear in documents.
-- Each one has case_id so it belongs to an investigation.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- persons
-- Any individual identified across source documents.
-- The aliases and role_tags columns use PostgreSQL arrays (TEXT[]) — a single
-- column that holds a list of values, like ["Jane Smith", "J. Smith"].
-- -----------------------------------------------------------------------------
CREATE TABLE persons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    full_name       VARCHAR(255) NOT NULL,
    aliases         TEXT[],                     -- other name spellings found
    role_tags       TEXT[],                     -- BOARD_MEMBER, SIGNER, DECEASED, etc.
    date_of_death   DATE,                       -- NULL if living; critical for sig verification
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN persons.date_of_death IS 'Populated when person is deceased. Used to flag impossible signatures on documents dated after death.';

CREATE INDEX idx_persons_case_id ON persons(case_id);


-- -----------------------------------------------------------------------------
-- organizations
-- Nonprofits, LLCs, government bodies, and any other corporate entity.
-- EIN = Employer Identification Number, found on IRS 990 filings.
-- -----------------------------------------------------------------------------
CREATE TABLE organizations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    name                VARCHAR(255) NOT NULL,
    org_type            org_type NOT NULL DEFAULT 'OTHER',
    ein                 VARCHAR(20),            -- e.g. "12-3456789"
    registration_state  CHAR(2),               -- two-letter state code
    status              org_status NOT NULL DEFAULT 'UNKNOWN',
    notes               TEXT,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_organizations_case_id ON organizations(case_id);


-- -----------------------------------------------------------------------------
-- properties
-- Real estate parcels. The valuation_delta is computed (purchase_price minus
-- assessed_value). A large negative delta means a property was sold well below
-- its assessed value — a potential red flag.
-- -----------------------------------------------------------------------------
CREATE TABLE properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    parcel_number   VARCHAR(50),                -- county auditor ID
    address         VARCHAR(500),
    county          VARCHAR(100),
    assessed_value  DECIMAL(12,2),             -- county's assessed value
    purchase_price  DECIMAL(12,2),             -- actual transaction price
    valuation_delta DECIMAL(12,2)
        GENERATED ALWAYS AS (purchase_price - assessed_value) STORED,
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN properties.valuation_delta IS 'Computed column: purchase_price - assessed_value. Negative = sold below assessed value.';

CREATE INDEX idx_properties_case_id ON properties(case_id);


-- -----------------------------------------------------------------------------
-- financial_instruments
-- UCC filings, liens, mortgages, loans. The signer_id, secured_party_id, and
-- debtor_id are all foreign keys that point back to either a person or org.
-- anomaly_flags is an array that the system populates automatically — e.g.
-- DECEASED_SIGNER gets added when the signer's date_of_death precedes
-- the filing_date.
-- -----------------------------------------------------------------------------
CREATE TABLE financial_instruments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    instrument_type     instrument_type NOT NULL DEFAULT 'OTHER',
    filing_number       VARCHAR(100),
    filing_date         DATE,
    signer_id           UUID REFERENCES persons(id) ON DELETE SET NULL,
    secured_party_id    UUID,                   -- can be person or org; resolved at app level
    debtor_id           UUID,                   -- same note
    amount              DECIMAL(12,2),
    anomaly_flags       TEXT[],                 -- DECEASED_SIGNER, DATE_MISMATCH, etc.
    notes               TEXT,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_financial_instruments_case_id ON financial_instruments(case_id);
CREATE INDEX idx_financial_instruments_signer ON financial_instruments(signer_id);


-- =============================================================================
-- JUNCTION / RELATIONSHIP TABLES
-- These tables wire entities to each other and to source documents.
-- A "junction table" has no independent existence — it just records a
-- relationship between two other things.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- person_document
-- "Person X appears in Document Y on page Z."
-- This is how we track citation-level provenance.
-- -----------------------------------------------------------------------------
CREATE TABLE person_document (
    person_id       UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_reference  VARCHAR(100),               -- e.g. "page 3, section 2"
    context_note    TEXT,                       -- brief note on how/why they appear
    PRIMARY KEY (person_id, document_id)        -- composite key: one row per pair
);

CREATE INDEX idx_person_document_doc ON person_document(document_id);


-- -----------------------------------------------------------------------------
-- org_document
-- Same pattern as person_document but for organizations.
-- -----------------------------------------------------------------------------
CREATE TABLE org_document (
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_reference  VARCHAR(100),
    context_note    TEXT,
    PRIMARY KEY (org_id, document_id)
);

CREATE INDEX idx_org_document_doc ON org_document(document_id);


-- -----------------------------------------------------------------------------
-- person_org
-- "Person X is the BOARD_MEMBER of Organization Y."
-- role describes the nature of the relationship.
-- -----------------------------------------------------------------------------
CREATE TABLE person_org (
    person_id   UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role        VARCHAR(100) NOT NULL,          -- BOARD_MEMBER, OFFICER, AGENT, etc.
    start_date  DATE,
    end_date    DATE,
    notes       TEXT,
    PRIMARY KEY (person_id, org_id, role)       -- same person can have multiple roles
);


-- -----------------------------------------------------------------------------
-- property_transaction
-- Records each ownership transfer of a property: who sold to whom, when, price.
-- Both buyer_id and seller_id can be a person OR org UUID — resolved in app.
-- -----------------------------------------------------------------------------
CREATE TABLE property_transaction (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
    transaction_date DATE,
    buyer_id        UUID,                       -- person or org UUID
    seller_id       UUID,                       -- person or org UUID
    price           DECIMAL(12,2),
    notes           TEXT
);

CREATE INDEX idx_property_transaction_property ON property_transaction(property_id);


-- -----------------------------------------------------------------------------
-- findings
-- The investigator's formal observations. Each finding links to specific
-- entities and documents, includes a narrative note, and can reference an
-- Ohio Revised Code section.
-- -----------------------------------------------------------------------------
CREATE TABLE findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    title           VARCHAR(500) NOT NULL,
    narrative       TEXT NOT NULL,
    orc_reference   VARCHAR(100),               -- e.g. "ORC 1716.15"
    severity        VARCHAR(50),                -- e.g. HIGH, MEDIUM, LOW — not an enum yet
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_findings_case_id ON findings(case_id);


-- -----------------------------------------------------------------------------
-- audit_log
-- APPEND-ONLY log of every significant action taken in the system.
-- The before_state and after_state columns store JSON snapshots so we can
-- reconstruct exactly what changed and when.
-- IMPORTANT: No application code should ever UPDATE or DELETE from this table.
-- -----------------------------------------------------------------------------
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID,                       -- NULL for system-level actions
    table_name      VARCHAR(100) NOT NULL,
    record_id       UUID,                       -- which row was affected
    action          VARCHAR(50) NOT NULL,       -- INSERT, UPDATE, DELETE, UPLOAD, etc.
    before_state    JSONB,                      -- snapshot before change (NULL for inserts)
    after_state     JSONB,                      -- snapshot after change (NULL for deletes)
    performed_by    VARCHAR(255),               -- username or 'system'
    performed_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ip_address      INET,                       -- optional: client IP
    notes           TEXT
);

COMMENT ON TABLE audit_log IS 'Append-only. Never UPDATE or DELETE rows here. This is the evidence chain.';

CREATE INDEX idx_audit_log_case_id ON audit_log(case_id);
CREATE INDEX idx_audit_log_performed_at ON audit_log(performed_at);
CREATE INDEX idx_audit_log_record ON audit_log(table_name, record_id);


-- =============================================================================
-- TRIGGER: auto-update updated_at on any table that has it
-- A trigger is a function the database runs automatically when something
-- happens — here, whenever a row is updated, it stamps the current time.
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply the trigger to every table that has an updated_at column
CREATE TRIGGER trg_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_properties_updated_at
    BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_financial_instruments_updated_at
    BEFORE UPDATE ON financial_instruments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_findings_updated_at
    BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- DONE
-- To verify: connect to your database and run \dt to list all tables,
-- or \d cases to inspect the cases table structure.
-- =============================================================================
