import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _build_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "lawmate-causelist-sync-lambda/1.0",
    }

    bearer_token = os.getenv("CAUSELIST_SYNC_BEARER_TOKEN", "").strip()
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    api_key = os.getenv("CAUSELIST_SYNC_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    return headers


def _sync_once() -> dict:
    base_url = os.getenv("CAUSELIST_SYNC_URL", "").strip()
    if not base_url:
        raise ValueError("CAUSELIST_SYNC_URL is required")

    source = os.getenv("CAUSELIST_SYNC_SOURCE", "daily").strip() or "daily"
    max_tabs = os.getenv("CAUSELIST_SYNC_MAX_TABS", "8").strip() or "8"
    timeout_seconds = int(os.getenv("CAUSELIST_SYNC_TIMEOUT_SECONDS", "45"))

    q = urllib.parse.urlencode({"source": source, "max_tabs": max_tabs})
    url = f"{base_url}?{q}" if "?" not in base_url else f"{base_url}&{q}"

    request = urllib.request.Request(
        url=url,
        data=b"{}",
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
        logger.info("Cause-list sync success: %s", result)
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "upstreamStatusCode": result["statusCode"],
            "upstreamBody": result["body"],
        }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception("Cause-list sync HTTP error")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": exc.code,
            "error": error_body,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cause-list sync failed")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": 500,
            "error": str(exc),
        }
