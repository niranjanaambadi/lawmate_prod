-- ============================================================
-- Legal Insight – Upload Support Migration
-- Allows jobs to be created from a direct PDF upload (no linked
-- Document record).  Run after legal_insight_migration.sql.
-- Run: psql -d <db> -f database/legal_insight_upload_migration.sql
-- ============================================================

-- 1. Make document_id nullable (upload jobs have no linked document)
ALTER TABLE legal_insight_jobs
  ALTER COLUMN document_id DROP NOT NULL;

-- 2. Add S3 location columns for uploaded PDFs
ALTER TABLE legal_insight_jobs
  ADD COLUMN IF NOT EXISTS upload_s3_key    VARCHAR(500),
  ADD COLUMN IF NOT EXISTS upload_s3_bucket VARCHAR(100);
