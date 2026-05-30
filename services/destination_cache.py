import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from config import Config
from models import db, CachedOption


def cache_is_fresh(provider: str, option_type: str, ttl_minutes: Optional[int] = None) -> bool:
    ttl_minutes = ttl_minutes if ttl_minutes is not None else Config.DESTINATION_CACHE_TTL_MINUTES
    newest = (
        CachedOption.query
        .filter_by(provider=provider, option_type=option_type)
        .order_by(CachedOption.updated_at.desc())
        .first()
    )
    if not newest or not newest.updated_at:
        return False

    updated_at = _ensure_aware(newest.updated_at)
    return updated_at >= datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)


def get_cached_options(provider: str, option_type: str) -> List[Dict[str, Any]]:
    rows = (
        CachedOption.query
        .filter_by(provider=provider, option_type=option_type)
        .order_by(CachedOption.name.asc())
        .all()
    )
    return [_row_to_dict(row) for row in rows]


def get_cached_option(provider: str, option_type: str, external_id: str) -> Optional[Dict[str, Any]]:
    if not external_id:
        return None
    row = CachedOption.query.filter_by(
        provider=provider,
        option_type=option_type,
        external_id=external_id,
    ).first()
    return _row_to_dict(row) if row else None


def upsert_cached_options(provider: str, option_type: str, options: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids = set()

    for option in options:
        external_id = str(option.get("id") or option.get("external_id") or "").strip()
        name = str(option.get("name") or option.get("title") or external_id).strip()
        if not external_id:
            continue

        seen_ids.add(external_id)
        row = CachedOption.query.filter_by(
            provider=provider,
            option_type=option_type,
            external_id=external_id,
        ).first()
        if not row:
            row = CachedOption(
                provider=provider,
                option_type=option_type,
                external_id=external_id,
                name=name,
            )
            db.session.add(row)

        row.name = name
        row.extra_json = json.dumps(option.get("extra") or {}, ensure_ascii=False)

    # Keep stale options instead of deleting them. This avoids accidental loss
    # when an API call is partial or a permission temporarily changes.
    db.session.commit()
    return get_cached_options(provider, option_type)


def _row_to_dict(row: CachedOption) -> Dict[str, Any]:
    try:
        extra = json.loads(row.extra_json or "{}")
    except Exception:
        extra = {}

    return {
        "id": row.external_id,
        "name": row.name,
        "provider": row.provider,
        "option_type": row.option_type,
        "extra": extra,
        "updated_at_utc": _ensure_aware(row.updated_at).isoformat() if row.updated_at else None,
    }


def _ensure_aware(value):
    if not value:
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
