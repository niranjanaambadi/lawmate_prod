-- Profile verification migration
-- Creates khc_advocates registry + user verification columns
-- Run with: psql "$DATABASE_URL" -f database/profile_verification_migration.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS profile_verified_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS verification_otp_code VARCHAR(10) NULL,
    ADD COLUMN IF NOT EXISTS verification_otp_expires_at TIMESTAMP NULL;

CREATE TABLE IF NOT EXISTS khc_advocates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    khc_advocate_id VARCHAR(50) NOT NULL UNIQUE,
    advocate_name VARCHAR(255) NOT NULL,
    mobile VARCHAR(15) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_khc_advocates_khc_advocate_id
    ON khc_advocates(khc_advocate_id);

INSERT INTO khc_advocates (khc_advocate_id, advocate_name, mobile, is_active)
VALUES ('K/000671/2018', 'Sanjay Johnson', '9567457405', TRUE)
ON CONFLICT (khc_advocate_id) DO UPDATE
SET advocate_name = EXCLUDED.advocate_name,
    mobile = EXCLUDED.mobile,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();
