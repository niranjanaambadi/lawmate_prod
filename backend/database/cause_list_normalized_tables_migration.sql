-- Normalized cause-list tables for schema-validated PDF pipeline
-- Run with: psql "$DATABASE_URL" -f database/cause_list_normalized_tables_migration.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cause_list_source') THEN
        CREATE TYPE cause_list_source AS ENUM ('daily', 'weekly', 'advanced', 'monthly');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS cause_lists (
    id UUID PRIMARY KEY,
    listing_date DATE NOT NULL,
    source cause_list_source NOT NULL,
    court_number VARCHAR(30),
    court_code VARCHAR(20),
    court_label VARCHAR(255),
    bench_name VARCHAR(255),
    cause_list_type VARCHAR(120),
    source_pdf_url TEXT,
    s3_bucket VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cause_lists_identity UNIQUE (listing_date, source, court_number, cause_list_type, s3_key)
);

CREATE TABLE IF NOT EXISTS case_items (
    id UUID PRIMARY KEY,
    cause_list_id UUID NOT NULL REFERENCES cause_lists(id) ON DELETE CASCADE,
    serial_number VARCHAR(30) NOT NULL,
    parent_serial_number VARCHAR(30),
    case_number_raw VARCHAR(120) NOT NULL,
    normalized_case_number VARCHAR(120) NOT NULL,
    case_type VARCHAR(50),
    case_number VARCHAR(40),
    case_year INTEGER,
    case_category VARCHAR(30),
    filing_mode VARCHAR(40),
    filing_mode_raw VARCHAR(80),
    bench_type VARCHAR(20),
    section_type VARCHAR(50),
    section_label VARCHAR(255),
    page_number INTEGER,
    item_no VARCHAR(30),
    party_names TEXT,
    petitioner_names JSONB,
    respondent_names JSONB,
    remarks TEXT,
    status VARCHAR(50),
    order_date DATE,
    next_listing_date DATE,
    interim_order_expiry DATE,
    urgent_memo_by VARCHAR(255),
    urgent_memo_service_status TEXT,
    mediation JSONB,
    arbitration JSONB,
    linked_cases JSONB,
    pending_compliance JSONB,
    raw_text TEXT,
    raw_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_case_items_causelist_serial_case UNIQUE (cause_list_id, serial_number, normalized_case_number)
);

CREATE TABLE IF NOT EXISTS advocates (
    id UUID PRIMARY KEY,
    name_raw VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255) NOT NULL,
    honorific VARCHAR(40),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_advocates_name_normalized UNIQUE (name_normalized)
);

CREATE TABLE IF NOT EXISTS case_advocates (
    id UUID PRIMARY KEY,
    case_item_id UUID NOT NULL REFERENCES case_items(id) ON DELETE CASCADE,
    advocate_id UUID NOT NULL REFERENCES advocates(id) ON DELETE CASCADE,
    side VARCHAR(20),
    role VARCHAR(80),
    role_raw VARCHAR(255),
    represented_parties TEXT[],
    is_served BOOLEAN,
    organization VARCHAR(255),
    is_lead_advocate BOOLEAN,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_case_advocates_item_adv_side UNIQUE (case_item_id, advocate_id, side)
);

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY,
    case_item_id UUID NOT NULL REFERENCES case_items(id) ON DELETE CASCADE,
    ia_number_raw VARCHAR(120) NOT NULL,
    ia_type VARCHAR(50),
    ia_number VARCHAR(30),
    ia_year INTEGER,
    ia_purpose TEXT,
    ia_status VARCHAR(50),
    ia_advocates JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_applications_item_ia UNIQUE (case_item_id, ia_number_raw)
);

CREATE INDEX IF NOT EXISTS ix_cause_lists_date_source ON cause_lists(listing_date, source);
CREATE INDEX IF NOT EXISTS ix_case_items_normalized_case_number ON case_items(normalized_case_number);
CREATE INDEX IF NOT EXISTS ix_case_items_cause_list_id ON case_items(cause_list_id);
CREATE INDEX IF NOT EXISTS ix_advocates_name_normalized ON advocates(name_normalized);
CREATE INDEX IF NOT EXISTS ix_case_advocates_case_item_id ON case_advocates(case_item_id);
CREATE INDEX IF NOT EXISTS ix_case_advocates_advocate_id ON case_advocates(advocate_id);
CREATE INDEX IF NOT EXISTS ix_applications_case_item_id ON applications(case_item_id);

