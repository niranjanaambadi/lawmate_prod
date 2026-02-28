"""
Custom validators
"""
import re
from fastapi import HTTPException


def validate_khc_id(khc_id: str) -> bool:
    """
    Validate KHC Advocate ID format
    Expected format: KHC/001/2020
    """
    pattern = r'^KHC/\d{3,}/\d{4}$'
    if not re.match(pattern, khc_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid KHC Advocate ID format. Expected: KHC/001/2020"
        )
    return True


def validate_case_number(case_number: str) -> bool:
    """
    Validate case number format
    Examples: WP(C) 123/2026, CRLA 456/2025
    """
    pattern = r'^[A-Z]+\([A-Z]\)?\s*\d+/\d{4}$'
    return bool(re.match(pattern, case_number))


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_mobile(mobile: str) -> bool:
    """
    Validate Indian mobile number
    Accepts: +919876543210 or 9876543210
    """
    pattern = r'^(\+91)?[6-9]\d{9}$'
    return bool(re.match(pattern, mobile))