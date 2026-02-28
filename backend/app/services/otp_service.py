from __future__ import annotations

import re
from typing import Dict

import httpx

from app.core.config import settings
from app.core.logger import logger


class OTPService:
    """OTP sender abstraction with provider toggle per channel."""

    def __init__(self) -> None:
        self.sms_provider = (settings.OTP_SMS_PROVIDER or "dev").strip().lower()
        self.email_provider = (settings.OTP_EMAIL_PROVIDER or "dev").strip().lower()

    def _normalize_phone(self, phone: str) -> str:
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) == 10:
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        if phone.startswith("+"):
            return phone
        return f"+{digits}" if digits else phone

    def send_sms_otp(self, phone: str, otp: str) -> Dict[str, str]:
        target = self._normalize_phone(phone)
        provider = self.sms_provider
        if provider == "dev":
            logger.info("[DEV OTP SMS] to=%s otp=%s", target, otp)
            return {"provider": "dev", "target": target}
        if provider == "twilio":
            sid = (settings.TWILIO_ACCOUNT_SID or "").strip()
            token = (settings.TWILIO_AUTH_TOKEN or "").strip()
            sender = (settings.OTP_SMS_FROM or "").strip()
            if not sid or not token or not sender:
                raise ValueError("Twilio SMS config missing (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/OTP_SMS_FROM)")
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            data = {
                "To": target,
                "From": sender,
                "Body": f"Your Lawmate verification OTP is {otp}. Valid for 5 minutes.",
            }
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, data=data, auth=(sid, token))
                if resp.status_code >= 400:
                    raise ValueError(f"Twilio SMS failed: {resp.status_code} {resp.text[:200]}")
            return {"provider": "twilio", "target": target}
        raise ValueError(f"Unsupported OTP_SMS_PROVIDER: {provider}")

    def send_email_otp(self, email: str, otp: str) -> Dict[str, str]:
        target = (email or "").strip()
        provider = self.email_provider
        if provider == "dev":
            logger.info("[DEV OTP EMAIL] to=%s otp=%s", target, otp)
            return {"provider": "dev", "target": target}
        if provider == "resend":
            api_key = (settings.RESEND_API_KEY or "").strip()
            sender = (settings.OTP_EMAIL_FROM or "").strip()
            if not api_key or not sender:
                raise ValueError("Resend email config missing (RESEND_API_KEY/OTP_EMAIL_FROM)")
            payload = {
                "from": sender,
                "to": [target],
                "subject": "Lawmate Verification OTP",
                "text": f"Your Lawmate verification OTP is {otp}. Valid for 5 minutes.",
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            with httpx.Client(timeout=20.0) as client:
                resp = client.post("https://api.resend.com/emails", json=payload, headers=headers)
                if resp.status_code >= 400:
                    raise ValueError(f"Resend email failed: {resp.status_code} {resp.text[:200]}")
            return {"provider": "resend", "target": target}
        raise ValueError(f"Unsupported OTP_EMAIL_PROVIDER: {provider}")


otp_service = OTPService()
