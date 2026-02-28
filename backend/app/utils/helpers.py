"""
Utility helper functions
"""
from datetime import datetime
import uuid
import re


def generate_uuid() -> str:
    """Generate UUID v4"""
    return str(uuid.uuid4())


def format_date(date: datetime, format_str: str = "%Y-%m-%d") -> str:
    """Format datetime object"""
    if not date:
        return None
    return date.strftime(format_str)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def truncate_text(text: str, length: int = 100) -> str:
    """Truncate text to specified length"""
    if len(text) <= length:
        return text
    return text[:length] + "..."