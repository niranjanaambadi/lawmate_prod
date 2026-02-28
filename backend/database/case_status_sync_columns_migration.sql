-- Add case status sync columns for dashboard-triggered sync pipeline
ALTER TABLE cases ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS next_hearing_date TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS court_status TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sync_error TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS raw_court_data JSONB;
