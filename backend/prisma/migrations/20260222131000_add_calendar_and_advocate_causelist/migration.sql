BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calendareventtype') THEN
    CREATE TYPE calendareventtype AS ENUM ('hearing','deadline','filing','reminder','meeting','other');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calendareventsource') THEN
    CREATE TYPE calendareventsource AS ENUM ('agent','manual','court_sync');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'advocatecauselistfetchstatus') THEN
    CREATE TYPE advocatecauselistfetchstatus AS ENUM ('fetched','failed');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS calendar_events (
  id UUID PRIMARY KEY,
  lawyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  case_id UUID NULL REFERENCES cases(id) ON DELETE SET NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT NULL,
  event_type calendareventtype NOT NULL DEFAULT 'other',
  source calendareventsource NOT NULL DEFAULT 'manual',
  start_datetime TIMESTAMP NOT NULL,
  end_datetime TIMESTAMP NULL,
  all_day BOOLEAN NOT NULL DEFAULT FALSE,
  location VARCHAR(255) NULL,
  google_event_id VARCHAR(255) NULL,
  google_synced_at TIMESTAMP NULL,
  google_sync_error TEXT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_calendar_events_lawyer_start
  ON calendar_events(lawyer_id, start_datetime);

CREATE INDEX IF NOT EXISTS ix_calendar_events_lawyer_type
  ON calendar_events(lawyer_id, event_type, is_active);

CREATE INDEX IF NOT EXISTS ix_calendar_events_case
  ON calendar_events(case_id, start_datetime);

CREATE INDEX IF NOT EXISTS ix_calendar_events_sync_pending
  ON calendar_events(lawyer_id, is_active, google_synced_at);

CREATE TABLE IF NOT EXISTS calendar_sync_tokens (
  id UUID PRIMARY KEY,
  lawyer_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  google_refresh_token_enc TEXT NOT NULL,
  google_access_token_enc TEXT NULL,
  google_token_expiry TIMESTAMP NULL,
  google_calendar_id VARCHAR(255) NOT NULL DEFAULT 'primary',
  google_sync_token TEXT NULL,
  last_synced_at TIMESTAMP NULL,
  last_sync_error TEXT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS advocate_cause_lists (
  id UUID PRIMARY KEY,
  lawyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  advocate_name VARCHAR(255) NOT NULL,
  advocate_code VARCHAR(50) NULL,
  date DATE NOT NULL,
  item_no INTEGER NULL,
  court_hall VARCHAR(100) NULL,
  court_hall_number INTEGER NULL,
  bench VARCHAR(20) NULL,
  list_type VARCHAR(100) NULL,
  judge_name VARCHAR(255) NULL,
  case_no VARCHAR(120) NULL,
  petitioner VARCHAR(255) NULL,
  respondent VARCHAR(255) NULL,
  fetch_status advocatecauselistfetchstatus NOT NULL DEFAULT 'fetched',
  fetch_error TEXT NULL,
  source_url TEXT NULL,
  fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_advocate_cause_lists_lawyer_adv_date_case UNIQUE (lawyer_id, advocate_name, date, case_no)
);

CREATE INDEX IF NOT EXISTS ix_advocate_cause_lists_lawyer_date
  ON advocate_cause_lists(lawyer_id, date);

CREATE INDEX IF NOT EXISTS ix_advocate_cause_lists_date_court
  ON advocate_cause_lists(date, court_hall_number);

CREATE INDEX IF NOT EXISTS ix_advocate_cause_lists_date_case
  ON advocate_cause_lists(date, case_no);

COMMIT;
