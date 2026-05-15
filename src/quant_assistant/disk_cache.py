from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

CACHE_DIR = Path("data/cache/history")
CACHE_TTL_DAYS = 7


def _cache_key(secid: str, start: str, end: str, adjust: str) -> str:
    return f"{secid}_{start}_{end}_{adjust}"


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.parquet"


def load_cached(secid: str, start: str, end: str, adjust: str) -> pd.DataFrame | None:
    key = _cache_key(secid, start, end, adjust)
    path = _cache_path(key)
    if not path.exists():
        return None
    # Check TTL
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    if datetime.now() - mtime > timedelta(days=CACHE_TTL_DAYS):
        path.unlink(missing_ok=True)
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def save_cached(secid: str, start: str, end: str, adjust: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    key = _cache_key(secid, start, end, adjust)
    path = _cache_path(key)
    frame.to_parquet(path, index=False)


def clear_expired_cache() -> int:
    """Remove expired cache files. Returns count removed."""
    if not CACHE_DIR.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
    removed = 0
    for path in CACHE_DIR.glob("*.parquet"):
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
