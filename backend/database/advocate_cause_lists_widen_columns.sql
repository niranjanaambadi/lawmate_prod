-- Widen advocate_cause_lists columns that are too narrow for actual KHC portal data.
--
-- bench was VARCHAR(20) — actual values include the full judge name, e.g.
--   "4855-HONOURABLE MR. JUSTICE C.PRATHEEP KUMAR" (46+ chars).
-- case_no was VARCHAR(120) — when portal columns shift, party names can land here
--   and exceed 120 chars.
-- petitioner/respondent were VARCHAR(255) — model defines them as Text; widen to match.

ALTER TABLE advocate_cause_lists
  ALTER COLUMN bench      TYPE VARCHAR(500),
  ALTER COLUMN case_no    TYPE VARCHAR(500),
  ALTER COLUMN petitioner TYPE TEXT,
  ALTER COLUMN respondent TYPE TEXT;
