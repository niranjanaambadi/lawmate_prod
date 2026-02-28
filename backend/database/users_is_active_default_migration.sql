-- Migration: Ensure users.is_active has a server-side DEFAULT TRUE
--
-- Why this is needed:
--   SQLAlchemy's Python-side `default=True` only fires when a record is
--   created through the ORM.  Raw SQL INSERTs (e.g. via Railway SQL console)
--   bypass it.  Adding a server-side DEFAULT guarantees that every INSERT
--   path produces an active account unless explicitly stated otherwise.
--
-- Safe to run multiple times — ALTER COLUMN ... SET DEFAULT is idempotent.

ALTER TABLE users
    ALTER COLUMN is_active SET DEFAULT TRUE;

-- Back-fill any existing inactive users that should be active
-- (comment this out if you intentionally have deactivated accounts)
UPDATE users
SET    is_active = TRUE
WHERE  is_active = FALSE;
