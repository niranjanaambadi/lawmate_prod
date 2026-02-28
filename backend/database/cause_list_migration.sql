-- Cause List: source-separated listing table
-- Run with: psql $DATABASE_URL -f database/cause_list_migration.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cause_list_source') THEN
        CREATE TYPE cause_list_source AS ENUM ('daily', 'weekly', 'advanced', 'monthly');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS cause_list_entries (
    id UUID PRIMARY KEY,
    case_number VARCHAR(100) NOT NULL,
    normalized_case_number VARCHAR(120) NOT NULL,
    listing_date DATE NOT NULL,
    source cause_list_source NOT NULL,
    court_number VARCHAR(50),
    bench_name VARCHAR(255),
    party_names TEXT,
    item_no VARCHAR(30),
    fetched_from_url TEXT,
    raw_data JSONB,
    ingestion_run_id UUID,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cause_list_case_date_source UNIQUE (
        normalized_case_number, listing_date, source, court_number, item_no
    )
);

ALTER TABLE cause_list_entries
ADD COLUMN IF NOT EXISTS ingestion_run_id UUID;

CREATE TABLE IF NOT EXISTS cause_list_ingestion_runs (
    id UUID PRIMARY KEY,
    source cause_list_source NOT NULL,
    listing_date DATE NOT NULL,
    fetched_from_url TEXT NOT NULL,
    s3_bucket VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL DEFAULT 'fetched',
    error TEXT,
    records_found INTEGER NOT NULL DEFAULT 0,
    records_upserted INTEGER NOT NULL DEFAULT 0,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    parsed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cause_list_date_source ON cause_list_entries(listing_date, source);
CREATE INDEX IF NOT EXISTS ix_cause_list_normalized_case_number ON cause_list_entries(normalized_case_number);
CREATE INDEX IF NOT EXISTS ix_cause_list_ingestion_source_date ON cause_list_ingestion_runs(source, listing_date);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_cause_list_ingestion_run'
          AND table_name = 'cause_list_entries'
    ) THEN
        ALTER TABLE cause_list_entries
        ADD CONSTRAINT fk_cause_list_ingestion_run
        FOREIGN KEY (ingestion_run_id)
        REFERENCES cause_list_ingestion_runs(id)
        ON DELETE SET NULL;
    END IF;
END$$;
