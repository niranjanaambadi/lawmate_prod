-- Hearing Day: hearing_notes and hearing_note_citations tables
-- Run with: psql $DATABASE_URL -f database/hearing_day_migration.sql

CREATE TABLE IF NOT EXISTS hearing_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content_json JSONB,
    content_text TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_hearing_notes_case_user UNIQUE (case_id, user_id)
);

CREATE INDEX ix_hearing_notes_case_user ON hearing_notes(case_id, user_id);

CREATE TABLE IF NOT EXISTS hearing_note_citations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hearing_note_id UUID NOT NULL REFERENCES hearing_notes(id) ON DELETE CASCADE,
    doc_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    quote_text TEXT,
    bbox_json JSONB,
    anchor_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_hearing_note_citations_note_id ON hearing_note_citations(hearing_note_id);
