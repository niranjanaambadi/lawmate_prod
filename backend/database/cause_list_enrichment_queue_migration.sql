-- Deferred LLM enrichment queue for cause-list rows
-- Run with: psql "$DATABASE_URL" -f database/cause_list_enrichment_queue_migration.sql

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'causelistenrichmentstatus'
    ) THEN
        CREATE TYPE causelistenrichmentstatus AS ENUM ('pending', 'processing', 'completed', 'failed');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS cause_list_enrichment_queue (
    id UUID PRIMARY KEY,
    ingestion_run_id UUID REFERENCES cause_list_ingestion_runs(id) ON DELETE SET NULL,
    case_item_id UUID NOT NULL UNIQUE REFERENCES case_items(id) ON DELETE CASCADE,
    listing_date DATE NOT NULL,
    source cause_list_source NOT NULL,
    court_number VARCHAR(30),
    serial_number VARCHAR(30),
    page_number INTEGER,
    row_snippet TEXT,
    row_text TEXT,
    status causelistenrichmentstatus NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    enriched_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_cause_enrich_status_created
  ON cause_list_enrichment_queue(status, created_at);

CREATE INDEX IF NOT EXISTS ix_cause_enrich_run_status
  ON cause_list_enrichment_queue(ingestion_run_id, status);

CREATE INDEX IF NOT EXISTS ix_cause_enrich_listing_source
  ON cause_list_enrichment_queue(listing_date, source);
