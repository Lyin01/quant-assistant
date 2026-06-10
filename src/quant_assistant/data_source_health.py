from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

CHINA_TZ = timezone(timedelta(hours=8))
HEALTH_FILE = Path("data_source_health.jsonl")


def record_request(provider: str, requested: int, success: int, failed: int, latency_ms: float) -> None:
    """Record a data source request outcome."""
    record = {
        "timestamp": datetime.now(CHINA_TZ).isoformat(),
        "provider": provider,
        "requested": requested,
        "success": success,
        "failed": failed,
        "latency_ms": latency_ms,
    }
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HEALTH_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_health(days: int = 7) -> list[dict[str, Any]]:
    """Read health records from the last N days."""
    if days <= 0:
        return []
    if not HEALTH_FILE.exists():
        return []
    cutoff = datetime.now(CHINA_TZ) - timedelta(days=days)
    records = []
    with open(HEALTH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    continue
                ts = datetime.fromisoformat(rec["timestamp"])
                if ts >= cutoff:
                    records.append(rec)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return records


def summarize_by_provider(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Summarize health records by provider. Returns {provider: {success_rate, avg_latency_ms}}."""
    from collections import defaultdict

    stats = defaultdict(lambda: {"total_requested": 0, "total_success": 0, "total_latency": 0.0, "count": 0})
    for rec in records:
        if not isinstance(rec, dict):
            continue
        provider = rec.get("provider") or "unknown"
        requested = _non_negative_number(rec.get("requested"))
        success = min(_non_negative_number(rec.get("success")), requested)
        stats[provider]["total_requested"] += requested
        stats[provider]["total_success"] += success
        stats[provider]["total_latency"] += _non_negative_number(rec.get("latency_ms"))
        stats[provider]["count"] += 1

    result = {}
    for provider, data in stats.items():
        requested = data["total_requested"]
        success = data["total_success"]
        count = data["count"]
        result[provider] = {
            "success_rate": (success / requested * 100) if requested > 0 else 0.0,
            "avg_latency_ms": (data["total_latency"] / count) if count > 0 else 0.0,
            "total_requests": requested,
        }
    return result


def _non_negative_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    return number
