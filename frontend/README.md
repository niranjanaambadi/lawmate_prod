# Lawmate Frontend

Next.js frontend that talks to the backend Auth API only. No Prisma or database in this app.

## Setup

1. Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` (e.g. `http://localhost:8000` when running the backend locally).
2. Optional for roster: set `KERALA_HC_ROSTER_PAGES` as comma-separated High Court URLs to scan for roster PDFs.
3. `npm install`
4. `npm run dev` — app runs at http://localhost:3000 (or next available port).

## Auth flow

- **Sign in** (`/signin`) — POST to backend `/api/v1/auth/login`, store JWT in `localStorage`, redirect to `/dashboard` or `callbackUrl`.
- **Sign up** (`/signup`) — POST to backend `/api/v1/auth/register`, then redirect to `/signin?registered=true`.
- **Forgot password** (`/forgot-password`) — POST to backend `/api/v1/auth/forgot-password`. Reset link (from email or dev console) goes to `/reset-password?token=...`.
- **Reset password** (`/reset-password?token=...`) — POST to backend `/api/v1/auth/reset-password`, then redirect to `/signin?reset=true`.
- **Dashboard** (`/dashboard`) — Protected; requires valid JWT. Unauthenticated users are redirected to `/signin?callbackUrl=/dashboard`.

## Backend

Ensure the backend is running (e.g. `cd backend && uvicorn app.main:app --reload`) and CORS allows the frontend origin. The backend owns the Prisma schema and database; run migrations from the backend repo.
