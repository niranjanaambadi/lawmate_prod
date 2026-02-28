-- Mediation List cases: case numbers extracted from the MEDIATION LIST
-- section at the end of the daily cause-list PDF.
--
-- Because advocate names are NOT printed in that section, we cannot match
-- them via normal name-search.  Instead:
--   1. The daily parse job stores raw case numbers here (fetch_status = 'pending').
--   2. A separate enrichment step (POST /cause-list/enrich-mediation) fetches
--      case details from the Kerala HC portal and populates petitioner_advocates
--      / respondent_advocates.
--   3. GET /cause-list then injects matching mediation cases into each
--      advocate's cause-list response at query time.

CREATE TABLE IF NOT EXISTS mediation_list_cases (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_date         DATE        NOT NULL,
  serial_number        VARCHAR(30) NOT NULL,
  case_number_raw      VARCHAR(120) NOT NULL,
  court_number         VARCHAR(30),
  raw_text             TEXT,

  -- Enrichment lifecycle: pending → fetching → fetched | failed
  fetch_status         VARCHAR(20) NOT NULL DEFAULT 'pending',
  fetch_attempts       INTEGER     NOT NULL DEFAULT 0,
  last_fetch_error     TEXT,
  fetched_at           TIMESTAMP,

  -- Populated after court portal fetch
  petitioner_names     JSONB,          -- list of party name strings
  respondent_names     JSONB,          -- list of party name strings
  petitioner_advocates JSONB,          -- list of advocate name strings
  respondent_advocates JSONB,          -- list of advocate name strings
  case_detail_raw      JSONB,          -- condensed enriched data snapshot

  created_at           TIMESTAMP   NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMP   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_mediation_list_date_case UNIQUE (listing_date, case_number_raw)
);

CREATE INDEX IF NOT EXISTS ix_mediation_list_date
  ON mediation_list_cases (listing_date);

CREATE INDEX IF NOT EXISTS ix_mediation_list_date_status
  ON mediation_list_cases (listing_date, fetch_status);

-- Optional: keep fetch_status values consistent via a check constraint.
ALTER TABLE mediation_list_cases
  DROP CONSTRAINT IF EXISTS ck_mediation_fetch_status;

ALTER TABLE mediation_list_cases
  ADD CONSTRAINT ck_mediation_fetch_status
  CHECK (fetch_status IN ('pending', 'fetching', 'fetched', 'failed'));
