CREATE TABLE IF NOT EXISTS tracked_cases (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  case_number VARCHAR(120) NOT NULL,
  case_type VARCHAR(50),
  case_year INTEGER,
  petitioner_name TEXT,
  respondent_name TEXT,
  status_text TEXT,
  stage VARCHAR(100),
  last_order_date TIMESTAMPTZ,
  next_hearing_date TIMESTAMPTZ,
  source_url TEXT,
  full_details_url TEXT,
  fetched_at TIMESTAMPTZ,
  is_visible BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_tracked_cases_user_case UNIQUE (user_id, case_number)
);

CREATE INDEX IF NOT EXISTS ix_tracked_cases_user_visible
  ON tracked_cases(user_id, is_visible);
