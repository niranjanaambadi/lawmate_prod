-- Remove legacy cause_list_entries table after normalized rollout.
-- Run with: psql "$DATABASE_URL" -f database/cause_list_legacy_cleanup_migration.sql

ALTER TABLE IF EXISTS cause_list_entries
  DROP CONSTRAINT IF EXISTS fk_cause_list_ingestion_run;

DROP INDEX IF EXISTS ix_cause_list_listing_advocate;
DROP INDEX IF EXISTS ix_cause_list_date_source;
DROP INDEX IF EXISTS ix_cause_list_normalized_case_number;

DROP TABLE IF EXISTS cause_list_entries;
