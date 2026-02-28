-- ============================================================
-- Legal Insight (Judgment Summarizer) Tables
-- Run: psql -d <db> -f database/legal_insight_migration.sql
-- ============================================================

-- Job status enum
DO $$ BEGIN
  CREATE TYPE legal_insight_job_status AS ENUM (
    'queued', 'extracting', 'ocr', 'summarizing', 'validating', 'completed', 'failed'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---- legal_insight_jobs ----
CREATE TABLE IF NOT EXISTS legal_insight_jobs (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  document_id      UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  status           legal_insight_job_status NOT NULL DEFAULT 'queued',
  progress         INTEGER     NOT NULL DEFAULT 0,
  model_id         VARCHAR(200) NOT NULL,
  prompt_version   VARCHAR(20) NOT NULL DEFAULT 'v1',
  error            TEXT,
  pdf_sha256       VARCHAR(64),
  created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
  completed_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_legal_insight_jobs_user_id     ON legal_insight_jobs (user_id);
CREATE INDEX IF NOT EXISTS ix_legal_insight_jobs_document_id ON legal_insight_jobs (document_id);
CREATE INDEX IF NOT EXISTS ix_legal_insight_jobs_status      ON legal_insight_jobs (status);
CREATE INDEX IF NOT EXISTS ix_legal_insight_jobs_sha_model   ON legal_insight_jobs (pdf_sha256, model_id, prompt_version);

-- ---- legal_insight_chunks ----
-- One row per text block; bbox stored as % of page dimensions (0–100).
CREATE TABLE IF NOT EXISTS legal_insight_chunks (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           UUID        NOT NULL REFERENCES legal_insight_jobs(id) ON DELETE CASCADE,
  chunk_id         VARCHAR(50) NOT NULL,   -- e.g. "chunk_000123"
  page_number      INTEGER     NOT NULL,
  bbox             JSONB,                  -- {x, y, width, height} in %
  text             TEXT        NOT NULL,
  char_start       INTEGER,
  char_end         INTEGER,
  parent_chunk_id  VARCHAR(50),
  created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_legal_insight_chunk_job_chunk UNIQUE (job_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS ix_legal_insight_chunks_job_chunk ON legal_insight_chunks (job_id, chunk_id);

-- ---- legal_insight_results ----
CREATE TABLE IF NOT EXISTS legal_insight_results (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           UUID        NOT NULL UNIQUE REFERENCES legal_insight_jobs(id) ON DELETE CASCADE,
  result_json      JSONB       NOT NULL,
  created_at       TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_legal_insight_results_job_id ON legal_insight_results (job_id);
