ALTER TABLE cause_list_entries
  ADD COLUMN IF NOT EXISTS cause_list_type TEXT,
  ADD COLUMN IF NOT EXISTS petitioner_name TEXT,
  ADD COLUMN IF NOT EXISTS respondent_name TEXT,
  ADD COLUMN IF NOT EXISTS advocate_names TEXT;

CREATE INDEX IF NOT EXISTS ix_cause_list_listing_advocate
  ON cause_list_entries (listing_date, lower(advocate_names));
