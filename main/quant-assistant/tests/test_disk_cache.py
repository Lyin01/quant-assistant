import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant_assistant.disk_cache import (
    CACHE_DIR,
    CACHE_TTL_DAYS,
    _cache_key,
    _cache_path,
    clear_expired_cache,
    load_cached,
    save_cached,
)


@pytest.fixture(autouse=True)
def clean_cache_dir():
    """Remove cache files before each test."""
    if CACHE_DIR.exists():
        for path in CACHE_DIR.glob("*.parquet"):
            path.unlink(missing_ok=True)
    yield
    if CACHE_DIR.exists():
        for path in CACHE_DIR.glob("*.parquet"):
            path.unlink(missing_ok=True)


def test_cache_key_format():
    key = _cache_key("1.000001", "2024-01-01", "2024-12-31", "qfq")
    assert key == "1.000001_2024-01-01_2024-12-31_qfq"


def test_cache_path_creates_dir():
    key = _cache_key("1.000001", "2024-01-01", "2024-12-31", "qfq")
    path = _cache_path(key)
    assert CACHE_DIR.exists()
    assert path.name == f"{key}.parquet"


def test_save_and_load_cached():
    frame = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "close": [100, 101, 102, 103, 104],
    })
    save_cached("1.000001", "2024-01-01", "2024-01-05", "qfq", frame)

    loaded = load_cached("1.000001", "2024-01-01", "2024-01-05", "qfq")
    assert loaded is not None
    assert len(loaded) == 5
    assert list(loaded["close"]) == [100, 101, 102, 103, 104]


def test_load_cached_miss():
    loaded = load_cached("1.999999", "2024-01-01", "2024-12-31", "qfq")
    assert loaded is None


def test_save_cached_empty_frame():
    empty = pd.DataFrame()
    save_cached("1.000001", "2024-01-01", "2024-12-31", "qfq", empty)
    # Should not create a file
    loaded = load_cached("1.000001", "2024-01-01", "2024-12-31", "qfq")
    assert loaded is None


def test_load_cached_expired():
    frame = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "close": [100, 101, 102, 103, 104],
    })
    save_cached("1.000001", "2024-01-01", "2024-01-05", "qfq", frame)

    # Manually set mtime to past TTL
    key = _cache_key("1.000001", "2024-01-01", "2024-01-05", "qfq")
    path = _cache_path(key)
    old_mtime = (datetime.now() - timedelta(days=CACHE_TTL_DAYS + 1)).timestamp()
    os.utime(path, (old_mtime, old_mtime))

    loaded = load_cached("1.000001", "2024-01-01", "2024-01-05", "qfq")
    assert loaded is None
    # File should be deleted
    assert not path.exists()


def test_clear_expired_cache():
    frame = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3),
        "close": [100, 101, 102],
    })
    # Save two files
    save_cached("1.000001", "2024-01-01", "2024-01-03", "qfq", frame)
    save_cached("1.000002", "2024-01-01", "2024-01-03", "qfq", frame)

    # Expire one
    key1 = _cache_key("1.000001", "2024-01-01", "2024-01-03", "qfq")
    path1 = _cache_path(key1)
    old_mtime = (datetime.now() - timedelta(days=CACHE_TTL_DAYS + 1)).timestamp()
    os.utime(path1, (old_mtime, old_mtime))

    removed = clear_expired_cache()
    assert removed == 1
    assert not path1.exists()

    # The other file should still exist
    loaded = load_cached("1.000002", "2024-01-01", "2024-01-03", "qfq")
    assert loaded is not None


def test_clear_expired_cache_empty_dir():
    removed = clear_expired_cache()
    assert removed == 0
