BEGIN;

CREATE TABLE IF NOT EXISTS case_notebooks (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_case_notebooks_user_case UNIQUE (user_id, case_id)
);

CREATE INDEX IF NOT EXISTS ix_case_notebooks_user_case
  ON case_notebooks (user_id, case_id);

CREATE TABLE IF NOT EXISTS notes (
  id UUID PRIMARY KEY,
  notebook_id UUID NOT NULL REFERENCES case_notebooks(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL DEFAULT 'Untitled',
  order_index INTEGER NOT NULL DEFAULT 0,
  content_json JSONB,
  content_text TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_notes_notebook_order
  ON notes (notebook_id, order_index);

-- Postgres full text index for notebook search
CREATE INDEX IF NOT EXISTS ix_notes_fts
  ON notes USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content_text, '')));

CREATE TABLE IF NOT EXISTS note_attachments (
  id UUID PRIMARY KEY,
  note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  file_url TEXT NOT NULL,
  s3_key TEXT,
  s3_bucket VARCHAR(100),
  file_name VARCHAR(255),
  content_type VARCHAR(100),
  file_size BIGINT,
  ocr_text TEXT,
  uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_note_attachments_note
  ON note_attachments (note_id);

COMMIT;
