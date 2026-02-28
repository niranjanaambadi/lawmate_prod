-- Live status session/captcha workflow migration
-- Run with: psql "$DATABASE_URL" -f database/live_status_session_migration.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE
    users_ref text;
    cases_ref text;
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

    SELECT format('%I.%I', n.nspname, c.relname)
      INTO cases_ref
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND lower(c.relname) = 'cases'
      AND n.nspname IN (current_schema(), 'public')
    ORDER BY CASE WHEN n.nspname = current_schema() THEN 0 ELSE 1 END
    LIMIT 1;

    IF users_ref IS NULL THEN
        RAISE EXCEPTION 'users table not found';
    END IF;

    IF cases_ref IS NULL THEN
        RAISE EXCEPTION 'cases table not found';
    END IF;

    EXECUTE format($SQL$
        CREATE TABLE IF NOT EXISTS court_session_status (
            user_id UUID PRIMARY KEY REFERENCES %s(id) ON DELETE CASCADE,
            session_cookies_enc TEXT,
            session_valid BOOLEAN NOT NULL DEFAULT FALSE,
            verified_at TIMESTAMP,
            expires_at TIMESTAMP,
            last_refresh_at TIMESTAMP,
            last_fetch_at TIMESTAMP,
            last_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    $SQL$, users_ref);

    EXECUTE format($SQL$
        CREATE TABLE IF NOT EXISTS court_fetch_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES %s(id) ON DELETE CASCADE,
            trigger_source VARCHAR(50) NOT NULL DEFAULT 'manual',
            requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            success BOOLEAN NOT NULL DEFAULT FALSE,
            fetched_cases INTEGER NOT NULL DEFAULT 0,
            updated_cases INTEGER NOT NULL DEFAULT 0,
            raw_html_s3_key TEXT,
            error TEXT
        )
    $SQL$, users_ref);
END
$$;

CREATE INDEX IF NOT EXISTS ix_court_fetch_runs_user_id ON court_fetch_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_court_fetch_runs_requested_at ON court_fetch_runs(requested_at);
