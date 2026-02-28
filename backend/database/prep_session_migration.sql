-- ============================================================
-- Case Prep AI — PrepSession table migration
-- Run: psql -d $DATABASE_URL -f database/prep_session_migration.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS prep_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id      UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode         VARCHAR(50)  NOT NULL DEFAULT 'argument_builder',
    document_ids UUID[]       NOT NULL DEFAULT '{}',
    messages     JSONB        NOT NULL DEFAULT '[]',
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_prep_sessions_user_case  ON prep_sessions (user_id, case_id);
CREATE INDEX IF NOT EXISTS ix_prep_sessions_case_id    ON prep_sessions (case_id);
CREATE INDEX IF NOT EXISTS ix_prep_sessions_user_id    ON prep_sessions (user_id);
