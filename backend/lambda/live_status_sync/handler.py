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
        "User-Agent": "lawmate-live-status-sync-lambda/1.0",
    }
    token = os.getenv("LIVE_STATUS_WORKER_TOKEN", "").strip()
    if token:
        headers["x-mcp-token"] = token
    return headers


def _run_once() -> dict:
    base_url = os.getenv("LIVE_STATUS_WORKER_URL", "").strip()
    if not base_url:
        raise ValueError("LIVE_STATUS_WORKER_URL is required")

    batch_size = os.getenv("LIVE_STATUS_BATCH_SIZE", "50").strip() or "50"
    timeout_seconds = int(os.getenv("LIVE_STATUS_TIMEOUT_SECONDS", "45"))

    q = urllib.parse.urlencode({"batch_size": batch_size})
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
        result = _run_once()
        finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("Live-status sync success: %s", result)
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "upstreamStatusCode": result["statusCode"],
            "upstreamBody": result["body"],
        }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception("Live-status sync HTTP error")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": exc.code,
            "error": error_body,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Live-status sync failed")
        return {
            "ok": False,
            "startedAt": started_at,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "statusCode": 500,
            "error": str(exc),
        }

