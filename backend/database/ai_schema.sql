-- prisma/migrations/[timestamp]_add_ai_insights_table/migration.sql

-- Add AI Insights table (new modular analysis system)
CREATE TABLE ai_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL,
    insight_type VARCHAR(50) NOT NULL,
    result JSONB NOT NULL,
    model VARCHAR(100) NOT NULL DEFAULT 'anthropic.claude-3-haiku-20240307-v1:0',
    tokens_used INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    error TEXT,
    cached BOOLEAN NOT NULL DEFAULT FALSE,
    cache_key VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,
    CONSTRAINT fk_ai_insights_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE INDEX idx_insight_case_type ON ai_insights(case_id, insight_type);
CREATE INDEX idx_insight_cache ON ai_insights(cache_key);
CREATE INDEX idx_insight_expires ON ai_insights(expires_at);

-- Add Hearing Briefs table
CREATE TABLE hearing_briefs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL,
    hearing_date TIMESTAMP NOT NULL,
    content TEXT NOT NULL,
    focus_areas TEXT[] NOT NULL DEFAULT '{}',
    bundle_snapshot JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_hearing_briefs_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
);

CREATE INDEX idx_brief_case_hearing ON hearing_briefs(case_id, hearing_date);

-- Add trigger for hearing_briefs updated_at
CREATE TRIGGER update_hearing_briefs_updated_at 
    BEFORE UPDATE ON hearing_briefs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Add AI metadata columns to documents table
ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS extracted_text TEXT,
    ADD COLUMN IF NOT EXISTS classification_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS ai_metadata JSONB;

-- Add index for document text search
CREATE INDEX idx_documents_text_search ON documents USING gin(to_tsvector('english', extracted_text))
    WHERE extracted_text IS NOT NULL;