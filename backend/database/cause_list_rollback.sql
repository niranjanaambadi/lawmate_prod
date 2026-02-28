-- Rollback Cause List table/type
-- Run with: psql $DATABASE_URL -f database/cause_list_rollback.sql

DROP INDEX IF EXISTS ix_cause_list_date_source;
DROP INDEX IF EXISTS ix_cause_list_normalized_case_number;
ALTER TABLE IF EXISTS cause_list_entries DROP CONSTRAINT IF EXISTS fk_cause_list_ingestion_run;
DROP TABLE IF EXISTS cause_list_entries;
DROP INDEX IF EXISTS ix_cause_list_ingestion_source_date;
DROP TABLE IF EXISTS cause_list_ingestion_runs;
DROP TYPE IF EXISTS cause_list_source;
