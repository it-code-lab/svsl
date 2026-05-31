from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime.

    SQLite often returns naive datetime objects even when SQLAlchemy columns are
    declared with DateTime(timezone=True). In this app, all saved scheduled
    values are intended to be UTC, so a naive value should be treated as UTC.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def ensure_utc_required(value: Optional[datetime], field_name: str = "datetime") -> datetime:
    normalized = ensure_utc(value)
    if normalized is None:
        raise ValueError(f"{field_name} is required")
    return normalized
