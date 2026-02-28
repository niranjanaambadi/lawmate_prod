-- Additional query indexes for normalized cause-list reads
-- Run with: psql "$DATABASE_URL" -f database/cause_list_query_indexes_migration.sql

CREATE INDEX IF NOT EXISTS ix_advocates_name_normalized
  ON advocates (name_normalized);

CREATE INDEX IF NOT EXISTS ix_case_advocates_case_item
  ON case_advocates (case_item_id, advocate_id);

CREATE INDEX IF NOT EXISTS ix_cause_lists_date
  ON cause_lists (listing_date);

CREATE INDEX IF NOT EXISTS ix_case_items_cause_list
  ON case_items (cause_list_id);

CREATE INDEX IF NOT EXISTS ix_case_items_type_year
  ON case_items (case_type, case_year);

CREATE INDEX IF NOT EXISTS ix_case_items_normalized_case
  ON case_items (normalized_case_number);

CREATE INDEX IF NOT EXISTS ix_cause_lists_court_date
  ON cause_lists (court_number, listing_date);

CREATE INDEX IF NOT EXISTS ix_case_items_status
  ON case_items (status);

CREATE INDEX IF NOT EXISTS ix_case_items_status_causelist
  ON case_items (status, cause_list_id);
