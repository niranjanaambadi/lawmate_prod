BEGIN;

CREATE TABLE IF NOT EXISTS hearing_note_enrichments (
  id UUID PRIMARY KEY,
  hearing_note_id UUID NOT NULL REFERENCES hearing_notes(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  model VARCHAR(120) NOT NULL DEFAULT 'deterministic',
  note_version INTEGER NOT NULL DEFAULT 1,
  citation_hash VARCHAR(64) NOT NULL DEFAULT '',
  enrichment_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status VARCHAR(30) NOT NULL DEFAULT 'completed',
  error TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_hearing_note_enrichments_note_updated
  ON hearing_note_enrichments (hearing_note_id, updated_at);

CREATE INDEX IF NOT EXISTS ix_hearing_note_enrichments_cache
  ON hearing_note_enrichments (hearing_note_id, note_version, citation_hash);

CREATE INDEX IF NOT EXISTS ix_hearing_note_enrichments_user
  ON hearing_note_enrichments (user_id);

COMMIT;
