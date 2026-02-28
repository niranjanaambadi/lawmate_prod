# Environment Variables for Deployment

**Backend:** Railway (with Postgres on Railway)  
**Frontend:** Vercel  
**DB:** Postgres (Railway)

---

## Railway (Backend)

Set these in your Railway project (backend service). Railway will also provide `DATABASE_URL` if you attach a Postgres plugin to the same project; otherwise set it manually.

### Required (no defaults in code)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Postgres connection string (Railway provides this when you add Postgres) | `postgresql://user:pass@host:port/railway` |
| `JWT_SECRET_KEY` | Secret for signing JWT tokens; use a long random string | (generate, e.g. `openssl rand -hex 32`) |
| `AWS_ACCESS_KEY_ID` | AWS credentials for S3 + Bedrock | Your IAM key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret for S3 + Bedrock | Your IAM secret |

### CORS (required for Vercel frontend)

| Variable | Description | Example |
|----------|-------------|---------|
| `CORS_ORIGINS` | JSON array of allowed origins (browser requests) | `["https://your-app.vercel.app","https://lawmate.in"]` |

### Optional but recommended for production

| Variable | Description | Default in code |
|----------|-------------|------------------|
| `DEBUG` | Set to `false` in production | `True` |
| `AWS_REGION` | AWS region for S3/Bedrock | `ap-south-1` |
| `BEDROCK_MODEL_ID` | Claude model for general AI | `anthropic.claude-3-haiku-...` |
| `S3_BUCKET_NAME` | Bucket for case PDFs | `lawmate-case-pdfs` |
| `ROSTER_S3_BUCKET_NAME` | Bucket for roster/causelist | `lawmate-khc-prod` |
| `CAUSELIST_S3_BUCKET_NAME` | Causelist storage | `lawmate-khc-prod` |

### Optional (feature-specific)

- **OTP (SMS/Email):** `OTP_SMS_PROVIDER`, `OTP_EMAIL_PROVIDER` (e.g. `twilio`, `resend`), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `RESEND_API_KEY`, `OTP_SMS_FROM`, `OTP_EMAIL_FROM`
- **Court / live status:** `LIVE_STATUS_COURT_BASE_URL`, `COURT_API_BASE_URL`, `COURT_API_KEY`, `PLAYWRIGHT_HEADLESS`, `CAPTCHA_ENABLED`, `TWOCAPTCHA_API_KEY`
- **Tavily (agent):** `TAVILY_API_KEY`, `TAVILY_ALLOWED_DOMAINS`
- **Google Calendar:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (if you use OAuth)
- **Legal Insight / Case Prep / Translation:** `LEGAL_INSIGHT_MODEL_ID`, `CASE_PREP_MODEL_ID`, `LEGAL_TRANSLATE_MODEL_ID`, `LEGAL_GLOSSARY_PATH`
- **Feature flag:** `HEARING_DAY_ENABLED` (e.g. `true`)

After deployment, note your backend URL (e.g. `https://your-backend.up.railway.app`) for the frontend.

---

## Vercel (Frontend)

Set these in the Vercel project (Dashboard → Settings → Environment Variables). Use **Production**, **Preview**, and **Development** as needed.

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL (no trailing slash). Used by the browser to call your Railway backend. | `https://your-backend.up.railway.app` |

### Optional

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_HEARING_DAY_ENABLED` | Show "Hearing Day" in sidebar when `true` | `true` or leave unset |

### Server-side only (if you use Next.js API routes that proxy to backend)

| Variable | Description | Example |
|----------|-------------|---------|
| `FASTAPI_INTERNAL_URL` | Backend URL used by Next.js server (e.g. agent proxy). Can be same as `NEXT_PUBLIC_API_URL` or an internal URL. | `https://your-backend.up.railway.app` |

---

## Checklist

**Railway (backend)**  
1. Create a Postgres database (or use existing); ensure `DATABASE_URL` is set (often auto-set by Railway).  
2. Set `JWT_SECRET_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.  
3. Set `CORS_ORIGINS` to include your Vercel URL (and custom domain if any), e.g. `["https://yourapp.vercel.app"]`.  
4. Deploy; copy the public backend URL.

**Vercel (frontend)**  
1. Set `NEXT_PUBLIC_API_URL` to your Railway backend URL (e.g. `https://xxx.up.railway.app`).  
2. Optionally set `NEXT_PUBLIC_HEARING_DAY_ENABLED` and `FASTAPI_INTERNAL_URL`.  
3. Deploy.

**Post-deploy**  
- Confirm frontend can sign in and call APIs (check browser Network tab for requests to `NEXT_PUBLIC_API_URL`).  
- Confirm backend logs show no CORS errors (if you see CORS errors, add the exact Vercel origin to `CORS_ORIGINS`).
