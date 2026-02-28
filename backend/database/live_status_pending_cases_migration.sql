-- Pending case statuses table for court-fetched rows
-- Run with: psql "$DATABASE_URL" -f database/live_status_pending_cases_migration.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE
    users_ref text;
BEGIN
    SELECT format('%I.%I', n.nspname, c.relname)
      INTO users_ref
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND lower(c.relname) = 'users'
      AND n.nspname IN (current_schema(), 'public')
    ORDER BY CASE WHEN n.nspname = current_schema() THEN 0 ELSE 1 END
    LIMIT 1;

    IF users_ref IS NULL THEN
        RAISE EXCEPTION 'users table not found';
    END IF;

    EXECUTE format($SQL$
        CREATE TABLE IF NOT EXISTS court_pending_case_statuses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES %s(id) ON DELETE CASCADE,
            case_number VARCHAR(120) NOT NULL,
            normalized_case_number VARCHAR(120) NOT NULL,
            status_text VARCHAR(120),
            stage VARCHAR(255),
            last_order_date TIMESTAMP,
            next_hearing_date TIMESTAMP,
            source_url TEXT,
            row_hash VARCHAR(64) NOT NULL,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    $SQL$, users_ref);
END
$$;

CREATE INDEX IF NOT EXISTS ix_court_pending_case_statuses_user_id
    ON court_pending_case_statuses(user_id);
CREATE INDEX IF NOT EXISTS ix_court_pending_case_statuses_case_number
    ON court_pending_case_statuses(case_number);
CREATE INDEX IF NOT EXISTS ix_court_pending_case_statuses_normalized_case_number
    ON court_pending_case_statuses(normalized_case_number);
CREATE UNIQUE INDEX IF NOT EXISTS ux_court_pending_case_statuses_user_case
    ON court_pending_case_statuses(user_id, normalized_case_number);
