import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant_assistant.disk_cache import (
    CACHE_DIR,
    CACHE_TTL_DAYS,
    _GENERIC_CACHE_DIR,
    _cache_key,
    _cache_path,
    _generic_cache_path,
    _safe_cache_key,
    clear_expired_cache,
    clear_generic_cache,
    load_generic_cache,
    load_cached,
    save_generic_cache,
    save_cached,
)


@pytest.fixture(autouse=True)
def isolated_cache_dirs(tmp_path, monkeypatch):
    """Keep cache tests away from the real workspace cache."""
    history_dir = tmp_path / "history"
    generic_dir = tmp_path / "generic"
    monkeypatch.setattr("quant_assistant.disk_cache.CACHE_DIR", history_dir)
    monkeypatch.setattr("quant_assistant.disk_cache._GENERIC_CACHE_DIR", generic_dir)
    globals()["CACHE_DIR"] = history_dir
    globals()["_GENERIC_CACHE_DIR"] = generic_dir
    if CACHE_DIR.exists():
        for path in CACHE_DIR.glob("*.parquet"):
            path.unlink(missing_ok=True)
    if _GENERIC_CACHE_DIR.exists():
        for path in _GENERIC_CACHE_DIR.glob("*.json"):
            path.unlink(missing_ok=True)


def test_cache_key_format():
    key = _cache_key("1.000001", "2024-01-01", "2024-12-31", "qfq")
    assert key == "1.000001_2024-01-01_2024-12-31_qfq"


def test_safe_cache_key_strips_path_fragments():
    assert _safe_cache_key("../evil/key") == "evil_key"
    assert _safe_cache_key("...") == "cache"


def test_cache_path_creates_dir():
    key = _cache_key("1.000001", "2024-01-01", "2024-12-31", "qfq")
    path = _cache_path(key)
    assert CACHE_DIR.exists()
    assert path.name == f"{key}.parquet"


def test_cache_path_keeps_path_fragments_inside_cache_dir():
    path = _cache_path("../evil/key")

    assert path.parent == CACHE_DIR
    assert path.name == "evil_key.parquet"
    assert path.resolve().is_relative_to(CACHE_DIR.resolve())


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


def test_save_and_load_generic_cache_with_sanitized_key():
    save_generic_cache("../macro/key", {"value": 1})

    path = _generic_cache_path("../macro/key")
    assert path.parent == _GENERIC_CACHE_DIR
    assert path.name == "macro_key.json"
    assert load_generic_cache("../macro/key") == {"value": 1}


def test_save_generic_cache_ignores_none():
    save_generic_cache("empty", None)

    assert not _generic_cache_path("empty").exists()


def test_clear_generic_cache_removes_existing_entry():
    save_generic_cache("clear-me", {"value": 1})

    assert load_generic_cache("clear-me") == {"value": 1}
    assert clear_generic_cache("clear-me") is True
    assert load_generic_cache("clear-me") is None
    assert clear_generic_cache("clear-me") is False
