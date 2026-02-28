# Hearing Day API

Feature flag: `HEARING_DAY_ENABLED` (default `True`). When `False`, hearing-day endpoints return 404.

## Endpoints

All require `Authorization: Bearer <token>`. Case/document ownership is enforced.

- **GET /api/v1/cases/search?q=&limit=**  
  Search cases by case number, e-filing number, party names. Returns `{ cases, items }`.

- **GET /api/v1/cases/{case_id}/documents**  
  List documents for a case. Returns `{ data, items }`.

- **GET /api/v1/hearing-day/{case_id}/note**  
  Get the current user’s hearing note for the case. 404 if none.

- **PUT /api/v1/hearing-day/{case_id}/note**  
  Create or update hearing note. Body: `content_json`, `content_text`, `version`. Optimistic lock: if `version` does not match the stored version, returns 409 with message to refresh.

- **POST /api/v1/hearing-day/{case_id}/citations**  
  Add a citation. Body: `hearing_note_id`, `doc_id`, `page_number`, optional `quote_text`, `bbox_json`, `anchor_id`.

- **GET /api/v1/hearing-day/{case_id}/citations**  
  List citations for the current user’s hearing note. Returns `{ data, items }`.

- **GET /api/v1/documents/{document_id}/view-url?expires_in=**  
  Return a short-lived signed URL to view the document. Do not store the URL; request a new one when needed.

## Page behavior (frontend)

- **/dashboard/hearing-day**  
  Search cases (debounced), select one, click “Proceed” → navigate to `/dashboard/hearing-day/[caseId]`.

- **/dashboard/hearing-day/[caseId]**  
  Two-column layout: left = document list + PDF viewer (iframe with view-url); right = notes editor with manual save. Autosave, text selection → citation, and citation jump are intended follow-ups.
