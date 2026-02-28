-- KHCAA directory enrichment migration
-- Run with: psql "$DATABASE_URL" -f database/khc_advocates_directory_migration.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS khc_advocates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    khc_advocate_id VARCHAR(50) NOT NULL UNIQUE,
    advocate_name VARCHAR(255) NOT NULL,
    mobile VARCHAR(15) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_khc_advocates_khc_advocate_id
    ON khc_advocates(khc_advocate_id);

ALTER TABLE khc_advocates
    ADD COLUMN IF NOT EXISTS email VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS source_member_id BIGINT NULL;

CREATE INDEX IF NOT EXISTS ix_khc_advocates_source_member_id
    ON khc_advocates(source, source_member_id);
