-- Daily cause list per advocate

CREATE TABLE IF NOT EXISTS daily_cause_lists (
  id UUID PRIMARY KEY,
  advocate_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  total_listings INTEGER NOT NULL DEFAULT 0,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  parse_error TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_daily_cause_lists_adv_date UNIQUE (advocate_id, date)
);

CREATE INDEX IF NOT EXISTS ix_daily_cause_lists_advocate_id ON daily_cause_lists (advocate_id);
CREATE INDEX IF NOT EXISTS ix_daily_cause_lists_date ON daily_cause_lists (date);
