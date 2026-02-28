-- Live Status tracking tables for server-side MCP polling
-- Run with: psql "$DATABASE_URL" -f database/live_status_migration.sql

DO $$
DECLARE
    ref_schema text;
    ref_table text;
    ref_qualified text;
BEGIN
    /*
      Auto-detect case table in current/public schema.
      Supports both:
      - cases  (SQLAlchemy/Prisma @@map)
      - "Case" (legacy Prisma model-name table)
    */
    SELECT n.nspname, c.relname
      INTO ref_schema, ref_table
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND lower(c.relname) = 'cases'
      AND n.nspname IN (current_schema(), 'public')
    ORDER BY CASE WHEN n.nspname = current_schema() THEN 0 ELSE 1 END
    LIMIT 1;

    IF ref_table IS NULL THEN
        RAISE EXCEPTION 'Could not find case table. Expected % or % in schema % or public.',
            'cases', '"Case"', current_schema();
    END IF;

    ref_qualified := format('%I.%I', ref_schema, ref_table);

    EXECUTE format($SQL$
        CREATE TABLE IF NOT EXISTS case_live_status_trackers (
            case_id UUID PRIMARY KEY REFERENCES %s(id) ON DELETE CASCADE,
            last_checked_at TIMESTAMP,
            next_check_at TIMESTAMP,
            last_status_hash VARCHAR(64),
            last_error TEXT,
            check_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            check_source VARCHAR(50) NOT NULL DEFAULT 'mcp',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    $SQL$, ref_qualified);

    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_case_live_status_trackers_next_check_at ON case_live_status_trackers(next_check_at)';

    EXECUTE format($SQL$
        CREATE TABLE IF NOT EXISTS case_live_status_snapshots (
            id UUID PRIMARY KEY,
            case_id UUID NOT NULL REFERENCES %s(id) ON DELETE CASCADE,
            status VARCHAR(50),
            next_hearing_date TIMESTAMP,
            bench_type VARCHAR(100),
            judge_name VARCHAR(255),
            court_number VARCHAR(50),
            source_url TEXT,
            snapshot_hash VARCHAR(64) NOT NULL,
            check_source VARCHAR(50) NOT NULL DEFAULT 'mcp',
            changed_fields TEXT[] NOT NULL DEFAULT '{}',
            raw_payload JSONB,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    $SQL$, ref_qualified);

    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_case_live_status_snapshots_case_id ON case_live_status_snapshots(case_id)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_case_live_status_snapshots_fetched_at ON case_live_status_snapshots(fetched_at)';
END
$$;
