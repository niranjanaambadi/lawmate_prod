# Multi-Tab Safety — Architecture

> **Scope:** This document describes every mechanism LawMate uses to keep data
> consistent when a lawyer has the same case open in multiple browser tabs
> simultaneously.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture Overview](#2-architecture-overview)
3. [Layer 1 — Auth / Session Consistency](#3-layer-1--auth--session-consistency)
4. [Layer 2 — Optimistic Concurrency](#4-layer-2--optimistic-concurrency)
5. [Layer 3 — Idempotency Keys](#5-layer-3--idempotency-keys)
6. [Layer 4 — Cross-Tab Cache Invalidation](#6-layer-4--cross-tab-cache-invalidation)
7. [Layer 5 — Draft Safety](#7-layer-5--draft-safety)
8. [Layer 6 — Polling Coordination (Leader Election)](#8-layer-6--polling-coordination-leader-election)
9. [Layer 7 — Backend Guarantees](#9-layer-7--backend-guarantees)
10. [Key Files Reference](#10-key-files-reference)
11. [Running Migrations](#11-running-migrations)
12. [Testing](#12-testing)

---

## 1. Problem Statement

A lawyer preparing for a hearing routinely opens the same case in two or more
browser tabs — one for the hearing notes editor, another for document review.
Without specific safeguards:

| Scenario | Consequence |
|---|---|
| Tab A and Tab B both edit the same hearing note | Last-writer wins; one set of edits is silently destroyed |
| Tab A logs out; Tab B continues to operate | Stale JWT is used until it expires; backend returns 401 |
| Two tabs hit the AI-enrich endpoint at the same time | Enrich job runs twice; duplicate Bedrock charges |
| Tab A saves a note; Tab B still shows the stale snapshot | Lawyer edits a version that is already out of date |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser                                 │
│                                                             │
│  Tab A              Tab B              Tab C                │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐        │
│  │ AuthCtx    │    │ AuthCtx    │    │ AuthCtx    │        │
│  │ useDraft   │    │ useDraft   │    │ useDraft   │        │
│  └─────┬──────┘    └─────┬──────┘    └─────┬──────┘        │
│        │                 │                 │                │
│  ┌─────▼─────────────────▼─────────────────▼──────┐        │
│  │           tabSync (TabSyncManager)              │        │
│  │   BroadcastChannel + localStorage fallback      │        │
│  │   Leader election via localStorage heartbeat    │        │
│  └──────────────────────────────────────────────── ┘        │
│                                                             │
│  sessionStorage: lawmate_tab_id (unique per tab)            │
│  localStorage:   lawmate_access_token                       │
│                  lawmate_tab_leader   (leader election)     │
│                  lawmate_refresh_lock (auth refresh mutex)  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS / JWT
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                          │
│                                                             │
│  CorrelationMiddleware (X-Correlation-ID, X-Tab-ID)         │
│  ─────────────────────────────────────────────────          │
│  DB: notes.version  (optimistic lock)                       │
│      hearing_notes.version                                  │
│      idempotency_records  (dedup)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1 — Auth / Session Consistency

### How it works

**File:** `frontend/src/contexts/AuthContext.tsx`

Every tab registers a `tabSync.subscribe()` listener in `AuthProvider`.

| Event | Broadcaster | Listener action |
|---|---|---|
| `AUTH_LOGOUT` | The tab that calls `logout()` | All other tabs clear token + user, redirect to `/signin` |
| `AUTH_TOKEN_UPDATE` | The tab that calls `login()` or receives a refreshed token | All other tabs adopt the new token; one tab (lock holder) calls `/me` |

### Cross-tab refresh lock

When the tab becomes visible after >30 s of inactivity, it re-validates the
session via `GET /api/v1/auth/me`.  To prevent all N tabs hitting the endpoint
simultaneously, a **mutex** is held in `localStorage`:

```
lawmate_refresh_lock = { id: <tabId>, ts: <timestamp> }
```

A tab only proceeds if the lock is absent or expired (5 s TTL).  After the
fetch completes the lock is released.

---

## 4. Layer 2 — Optimistic Concurrency

### Database schema

Both editable resources carry an integer `version` column:

```sql
-- Notes (case notebooks)
ALTER TABLE notes ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- Hearing notes (added in a prior migration)
-- hearing_notes.version already exists
```

Every successful `PUT` increments the version:
```python
note.version = (note.version or 1) + 1
```

### Backend check

**Files:** `backend/app/api/v1/endpoints/notebooks.py`,
`backend/app/api/v1/endpoints/hearing_day.py`

```python
if payload.version is not None and note.version != payload.version:
    raise HTTPException(
        status_code=409,
        detail={
            "message": "This note was updated in another tab. Reload the latest version before saving.",
            "current_version": note.version,
            "current_record": { ... },   # full latest snapshot
        },
    )
```

### Frontend handling

**Files:** `frontend/src/lib/api.ts` (`ConflictError`),
`frontend/src/components/ConflictModal.tsx`

`apiRequest()` detects HTTP 409 and throws `ConflictError`:

```typescript
if (res.status === 409) {
  const body = await res.json();
  throw new ConflictError({ message, current_version, current_record });
}
```

The calling component catches `ConflictError` and opens `<ConflictModal>`:

```typescript
try {
  await updateNotebookNote(noteId, { ...payload, version: note.version }, token);
} catch (err) {
  if (err instanceof ConflictError) {
    setConflict(err.payload);   // opens ConflictModal
  }
}
```

`ConflictModal` offers three choices:

| Button | Action |
|---|---|
| **Reload latest** | Replaces local editor state with `current_record` from the 409 payload |
| **Keep my version** | Re-submits the save with `version` omitted (bypasses check) |
| **Cancel** | Dismisses without action |

---

## 5. Layer 3 — Idempotency Keys

Certain endpoints are expensive and must not run twice if two tabs race:

- `POST /api/v1/hearing-day/{caseId}/enrich`
- `POST /api/v1/translate/text` (large documents)
- `POST /api/v1/ai-insights/sync` (case sync)

### Database table

```sql
CREATE TABLE idempotency_records (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key  VARCHAR(255) NOT NULL,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint         VARCHAR(255),
    status_code      INTEGER NOT NULL DEFAULT 200,
    response_body    JSONB   NOT NULL DEFAULT '{}',
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMP NOT NULL,
    UNIQUE (idempotency_key, user_id)
);
```

### Service API

**File:** `backend/app/services/idempotency_service.py`

```python
# In an endpoint:
cached = get_idempotent_response(key, current_user.id, db)
if cached:
    status_code, body = cached
    return JSONResponse(body, status_code=status_code)

result = do_expensive_work(...)

store_idempotent_response(key, current_user.id, 200, result, db)
return result
```

`store_idempotent_response` silently absorbs `IntegrityError` so a race
between two identical requests never crashes — the first writer wins.

Records expire after **24 hours** and are swept by a background task in
`main.py` every hour.

---

## 6. Layer 4 — Cross-Tab Cache Invalidation

**Files:** `frontend/src/lib/tabSync.ts`,
`frontend/src/hooks/useCrossTabInvalidation.ts`

After any mutation (create / update / delete), the mutating tab broadcasts:

```typescript
tabSync?.broadcast({ type: "CACHE_INVALIDATE", resource: "cases" });
// or for a specific record:
tabSync?.broadcast({ type: "CACHE_INVALIDATE", resource: "notes", id: noteId });
```

Other tabs receive this and trigger a refetch:

```typescript
const { invalidate } = useCrossTabInvalidation("cases", fetchCases);

// After saving:
await saveCase();
invalidate();          // tells all other tabs to refetch "cases"
```

---

## 7. Layer 5 — Draft Safety

**File:** `frontend/src/hooks/useDraftSafety.ts`

Prevents two tabs silently editing the same note at the same time.

```typescript
const { isDirty, isLockedByOtherTab, acquireLock, releaseLock, markDirty, markClean }
  = useDraftSafety("note", noteId);

// On editor focus:
acquireLock();   // broadcasts DRAFT_LOCK_ACQUIRED → other tabs see isLockedByOtherTab

// On blur / save:
releaseLock();   // broadcasts DRAFT_LOCK_RELEASED
markClean();
```

| State | Meaning |
|---|---|
| `isDirty` | Local unsaved changes exist; shows "Unsaved changes" indicator |
| `isLockedByOtherTab` | Another tab is actively editing this resource; shows warning banner |

The hook also installs a `beforeunload` guard when `isDirty` is true to
prevent accidental navigation.

---

## 8. Layer 6 — Polling Coordination (Leader Election)

**File:** `frontend/src/lib/tabSync.ts`

Only one tab should poll the backend for case status updates, push
notifications, etc.  The leader is elected via a **localStorage heartbeat**:

```
lawmate_tab_leader = { id: <tabId>, ts: <timestamp> }
```

- Heartbeat interval: **2 s**
- TTL: **6 s** (after 6 s without a heartbeat, the leader is considered dead)
- Any tab can check `tabSync.isLeader`
- On `beforeunload`, the leader releases the key so another tab can claim it
  immediately

**File:** `frontend/src/hooks/useVisibilityRefresh.ts`

A complementary hook for non-polling data: triggers a refetch when the user
returns to the tab after ≥ 30 s of inactivity.

---

## 9. Layer 7 — Backend Guarantees

### Correlation IDs

**File:** `backend/app/middleware/correlation.py`

Every HTTP request is assigned a `X-Correlation-ID` (accepted from the client
or generated fresh).  The `X-Tab-ID` is read from the client and echoed back.
Both are attached to structured logs so a single request can be traced across
all log lines regardless of which tab produced it.

### Database transaction boundaries

All notebook and hearing-day endpoints use a single `db.commit()` per request.
Version increments are done inside the same transaction as the content update,
preventing partial writes.

### Unique constraints

```sql
UNIQUE (idempotency_key, user_id)  -- prevents duplicate idempotency inserts
```

---

## 10. Key Files Reference

| File | Purpose |
|---|---|
| `frontend/src/lib/tabSync.ts` | Core BroadcastChannel + leader election singleton |
| `frontend/src/contexts/AuthContext.tsx` | Cross-tab login/logout, visibility refresh |
| `frontend/src/hooks/useCrossTabInvalidation.ts` | Subscribe to + broadcast cache invalidation |
| `frontend/src/hooks/useVisibilityRefresh.ts` | Refetch on tab focus if data is stale |
| `frontend/src/hooks/useDraftSafety.ts` | Per-tab draft lock + unsaved changes indicator |
| `frontend/src/components/ConflictModal.tsx` | 409 conflict resolution UI |
| `frontend/src/lib/api.ts` | `ConflictError` class, `X-Tab-ID` header injection |
| `backend/app/middleware/correlation.py` | `X-Correlation-ID` / `X-Tab-ID` middleware |
| `backend/app/services/idempotency_service.py` | Idempotency cache get/store/cleanup |
| `backend/app/api/v1/endpoints/notebooks.py` | Version check on `PUT /notes/{id}` |
| `backend/app/api/v1/endpoints/hearing_day.py` | Version check on `PUT /{caseId}/note` |
| `backend/app/db/models.py` | `Note.version`, `IdempotencyRecord` model |
| `backend/scripts/migrate_multi_tab.py` | DB migration: version column + idempotency table |
| `backend/tests/test_multi_tab.py` | Pytest suite for all multi-tab safety concerns |

---

## 11. Running Migrations

```bash
# Standard run (applies changes):
python backend/scripts/migrate_multi_tab.py

# Dry-run (prints SQL without executing):
python backend/scripts/migrate_multi_tab.py --dry-run

# Custom database URL:
DATABASE_URL=postgresql://user:pass@host/db python backend/scripts/migrate_multi_tab.py
```

The migration is **idempotent** — safe to re-run.

---

## 12. Testing

```bash
# Run multi-tab safety tests only:
pytest backend/tests/test_multi_tab.py -v

# Run all tests:
pytest backend/tests/ -v
```

The test suite covers:
- `IdempotencyService` unit tests (mock DB)
- `CorrelationMiddleware` header injection (mini FastAPI app)
- Notebook version conflict endpoint (auth override)
- Simultaneous idempotency saves (race condition simulation)
- Migration script dry-run smoke test
