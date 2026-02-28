from __future__ import annotations

import re
import time
import base64
from typing import Optional

import boto3
import httpx

from app.core.config import settings
from app.core.logger import logger


class CaptchaSolverService:
    def __init__(self) -> None:
        self.enabled = bool(settings.CAPTCHA_ENABLED)
        self.twocaptcha_key = (settings.TWOCAPTCHA_API_KEY or "").strip()
        self._rekognition = None

    def _rekognition_client(self):
        if self._rekognition is None:
            self._rekognition = boto3.client("rekognition", region_name=settings.AWS_REGION)
        return self._rekognition

    def _normalize_guess(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", value or "").strip()

    def _solve_with_rekognition(self, image_bytes: bytes) -> Optional[str]:
        try:
            result = self._rekognition_client().detect_text(Image={"Bytes": image_bytes})
            detections = result.get("TextDetections") or []
            lines = []
            for d in detections:
                if (d.get("Type") or "").upper() != "LINE":
                    continue
                if float(d.get("Confidence") or 0.0) < 60.0:
                    continue
                lines.append(d.get("DetectedText") or "")
            guess = self._normalize_guess("".join(lines))
            if len(guess) >= 4:
                return guess
        except Exception as exc:
            logger.warning("Rekognition captcha solve failed: %s", str(exc))
        return None

    def _solve_with_2captcha(self, image_bytes: bytes) -> Optional[str]:
        if not self.twocaptcha_key:
            return None
        try:
            with httpx.Client(timeout=30.0) as client:
                submit = client.post(
                    "https://api.2captcha.com/in.php",
                    data={
                        "key": self.twocaptcha_key,
                        "method": "base64",
                        "body": base64.b64encode(image_bytes).decode("ascii"),
                        "json": "1",
                    },
                )
                submit.raise_for_status()
                submit_json = submit.json()
                if int(submit_json.get("status", 0)) != 1:
                    return None

                task_id = str(submit_json.get("request") or "").strip()
                if not task_id:
                    return None

                for _ in range(12):
                    time.sleep(5)
                    poll = client.get(
                        "https://api.2captcha.com/res.php",
                        params={"key": self.twocaptcha_key, "action": "get", "id": task_id, "json": "1"},
                    )
                    poll.raise_for_status()
                    poll_json = poll.json()
                    if int(poll_json.get("status", 0)) == 1:
                        guess = self._normalize_guess(str(poll_json.get("request") or ""))
                        if len(guess) >= 4:
                            return guess
                        return None
                    if str(poll_json.get("request")) != "CAPCHA_NOT_READY":
                        return None
        except Exception as exc:
            logger.warning("2captcha solve failed: %s", str(exc))
        return None

    def solve(self, image_bytes: bytes) -> Optional[str]:
        if not self.enabled or not image_bytes:
            return None
        guess = self._solve_with_rekognition(image_bytes)
        if guess:
            return guess
        return self._solve_with_2captcha(image_bytes)


captcha_solver_service = CaptchaSolverService()
