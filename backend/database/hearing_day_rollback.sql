-- Rollback Hearing Day tables
-- Run with: psql $DATABASE_URL -f database/hearing_day_rollback.sql

DROP INDEX IF EXISTS ix_hearing_note_citations_note_id;
DROP TABLE IF EXISTS hearing_note_citations;

DROP INDEX IF EXISTS ix_hearing_notes_case_user;
DROP TABLE IF EXISTS hearing_notes;
