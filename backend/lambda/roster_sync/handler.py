import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone


logger = logging.getLogger()
logger.setLevel(logging.INFO)

"""For this Lambda worker, use these env vars:

ROSTER_SYNC_URL (required)
Full backend endpoint, e.g. https://api.yourdomain.com/api/v1/roster/sync

ROSTER_SYNC_BEARER_TOKEN (optional)
If your backend expects Authorization: Bearer <token>

ROSTER_SYNC_API_KEY (optional)
If your backend expects x-api-key: <key>

ROSTER_SYNC_TIMEOUT_SECONDS (optional, default 30)
HTTP timeout for the sync call
Once backend is live (Railway or similar), set ROSTER_SYNC_URL to that public /api/v1/roster/sync URL and deploy the Lambda stack in ap-south-1; the 30-minute schedule will keep S3 updated automatically.
If your backend endpoint is public and unprotected, only ROSTER_SYNC_URL is mandatory.
Use this checklist when ready.

1. Backend URL example  
`https://your-backend.up.railway.app/api/v1/roster/sync`

2. Deploy commands  
```bash
cd /Users/niranjanaambadi/Documents/latest_lawmate/backend/lambda/roster_sync
sam build
sam deploy --guided
```

3. Exact `sam deploy --guided` answers
- `Stack Name`: `lawmate-roster-sync`
- `AWS Region`: `ap-south-1`
- `Confirm changes before deploy`: `Y` (or `N` if you prefer fast deploy)
- `Allow SAM CLI IAM role creation`: `Y`
- `Disable rollback`: `N`
- `RosterSyncUrl`: `https://your-backend.up.railway.app/api/v1/roster/sync`
- `RosterSyncBearerToken`: `<leave empty if not needed>`
- `RosterSyncApiKey`: `<leave empty if not needed>`
- `Save arguments to configuration file`: `Y`

4. One-time test  
```bash
aws lambda invoke \
  --function-name lawmate-roster-sync \
  --region ap-south-1 \
  --payload '{}' \
  /tmp/roster-sync-response.json && cat /tmp/roster-sync-response.json
```

5. Verify S3 outputs
- `s3://lawmate-khc-prod/roster/latest.pdf`
- `s3://lawmate-khc-prod/roster/latest.json`
- `s3://lawmate-khc-prod/roster/<YYYY-MM-DD>/<filename>.pdf`

6. Optional manual trigger later
```bash
aws events list-rules --name-prefix lawmate-roster-sync --region ap-south-1
```
The schedule is already `rate(30 minutes)` from the template.
"""
def _build_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "lawmate-roster-sync-lambda/1.0",
    }

    bearer_token = os.getenv("ROSTER_SYNC_BEARER_TOKEN", "").strip()
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    api_key = os.getenv("ROSTER_SYNC_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    return headers


def _sync_once() -> dict:
    url = os.getenv("ROSTER_SYNC_URL", "").strip()
    if not url:
        raise ValueError("ROSTER_SYNC_URL is required")

    timeout_seconds = int(os.getenv("ROSTER_SYNC_TIMEOUT_SECONDS", "30"))
    payload = json.dumps({"source": "lambda-scheduler"}).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers=_build_headers(),
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")
        status_code = getattr(response, "status", 200)
        body = json.loads(raw) if raw else {}
        return {"statusCode": status_code, "body": body}


def handler(event, context):  # noqa: ANN001
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = _sync_once()
        finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("Roster sync success: %s", result)
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "upstreamStatusCode": result["statusCode"],
            "upstreamBody": result["body"],
        }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception("Roster sync HTTP error")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": exc.code,
            "error": error_body,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Roster sync failed")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": 500,
            "error": str(exc),
        }
