"""
Helper to read integration config values from DB with a 60-second TTL cache.
Falls back to the provided default if no DB row exists or the value is null.

Usage:
    from app.db.integration_config_helper import get_integration_value
    token = get_integration_value("GITHUB_TOKEN", fallback=settings.GITHUB_TOKEN)
"""
import time
from typing import Optional

_cache: dict[str, tuple[Optional[str], float]] = {}
_CACHE_TTL = 60.0


def get_integration_value(key: str, fallback: Optional[str] = None) -> Optional[str]:
    now = time.monotonic()
    if key in _cache:
        cached_value, ts = _cache[key]
        if now - ts < _CACHE_TTL:
            return cached_value if cached_value is not None else fallback

    from app.db.session import SessionLocal
    from app.models.integration_config import IntegrationConfig

    db = SessionLocal()
    try:
        row = db.query(IntegrationConfig).filter(IntegrationConfig.key == key).first()
        value = row.value if row else None
        _cache[key] = (value, now)
        return value if value is not None else fallback
    finally:
        db.close()


def invalidate_cache(key: Optional[str] = None) -> None:
    """Call after updating a value via API so the next read is fresh."""
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()
