# Extension <-> Backend Compatibility Checklist

Use this checklist before releasing extension or backend changes.

## 1) Base URL and API Prefix

- `API_BASE_URL` in extension points to deployed backend domain.
- Backend mounts routes under `/api/v1`.
- Extension endpoint constants match backend routes:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/identity/verify`
  - `POST /api/v1/sync/cases`
  - `POST /api/v1/sync/documents`
  - `POST /api/v1/upload/presigned-url`
  - `POST /api/v1/upload/multipart/init`
  - `POST /api/v1/upload/multipart/complete`
  - `DELETE /api/v1/upload/multipart/abort/{upload_id}`

## 2) Auth Contract

- Login response includes:
  - `access_token`
  - `user` object with `khc_advocate_id` and `khc_advocate_name`
- If backend does not support refresh endpoint:
  - Extension `REFRESH` is `null`
  - Extension must decode JWT `exp` and force re-login after expiry.

## 3) Identity Verification Contract

- Extension sends:
  - query param `scraped_khc_id`
  - JSON body may include `scraped_name`
- Backend returns:
  - success: `{ verified: true, ... }`
  - mismatch/error: non-2xx or `{ verified: false, ... }`
- Backend must validate authenticated user’s `khc_advocate_id` against `scraped_khc_id`.

## 4) Case Sync Contract (`/sync/cases`)

- Extension payload includes:
  - `efiling_number`, `case_number`, `case_type`, `case_year`
  - `party_role`, `petitioner_name`, `respondent_name`
  - `efiling_date`, `status`
  - optional `efiling_details`, `next_hearing_date`, `bench_type`, `judge_name`, `khc_source_url`
  - `khc_id`
- Backend behavior:
  - upsert by user + efiling identifier
  - enforce `khc_id` ownership
  - return 2xx on create/update

## 5) Document Sync Contract (`/sync/documents`)

- Extension payload includes:
  - `case_number` (or efiling number fallback in backend)
  - `khc_document_id`
  - `category`, `title`
  - `s3_key`, `file_size`
  - optional `source_url`
- Backend behavior:
  - resolve correct case owned by authenticated user
  - upsert document by `(case_id, khc_document_id)`
  - mark upload status completed

## 6) Upload Contract

- Standard upload:
  - request: `case_number`, `document_id`, `file_size`, optional `content_type`
  - response includes `upload_url`, `s3_key`
- Multipart init:
  - response includes `upload_id`, `chunk_urls[]`, `s3_key`, `total_parts`
- Multipart complete:
  - request includes sorted `parts: [{ PartNumber, ETag }]`
- Abort:
  - endpoint accepts `upload_id` path and `s3_key` query/body as implemented.

## 7) Message/Status Contract (Extension Internal)

- Message actions exist on both sender and receiver:
  - `VERIFY_IDENTITY`, `SYNC_CASES`
  - `UPDATE_STATUS`, `UPDATE_PROGRESS`
  - `TRIGGER_AUTO_SYNC`, `SYNC_SELECTED_CASE`
- UI status mapping supports:
  - `pending`, `syncing`, `uploading`, `failed`
  - success aliases: `success` and `completed`

## 8) Preference Contract

- Auto-sync toggle persists to:
  - `chrome.storage.local.auto_sync`
  - `user_profile.preferences.auto_sync` (for compatibility)
- Content script reads both keys with deterministic fallback.

## 9) Manual Smoke Test (Must Pass)

- Login succeeds and popup shows user KHC ID.
- Open KHC `my_cases` page and extension initializes without errors.
- Identity verification succeeds for matching account.
- Clicking `Sync Now` starts sync and updates row statuses.
- At least one document uploads to S3 and appears in backend DB.
- Context-menu "Sync this case to Lawmate" triggers selected-case sync.
- Auto-sync works when enabled and does not trigger when disabled.
- Expired JWT causes clean failure + re-login path (no crash loop).

## 10) Regression Gate (Release Checklist)

- No endpoint path changes without updating `extension/src/utils/constants.js`.
- No request schema changes without updating:
  - `extension/src/background/sync-manager.js`
  - `extension/src/background/upload-manager.js`
- No auth response changes without updating:
  - `extension/src/background/auth-manager.js`
  - `extension/src/popup/popup.js`
- Build succeeds and extension loads in Chrome without runtime console errors.
