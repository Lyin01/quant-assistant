from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


CHINA_TZ = timezone(timedelta(hours=8))
HISTORY_FILE = Path("portfolio_history.jsonl")


def compute_delta(
    existing_positions: list[dict[str, Any]],
    imported_positions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Compare existing and imported positions, return lists of added/updated/removed names."""
    existing_by_name = {p["name"]: p for p in existing_positions if p.get("name")}
    imported_by_name = {p["name"]: p for p in imported_positions if p.get("name")}

    added = []
    updated = []
    removed = []

    for name, imp in imported_by_name.items():
        if name not in existing_by_name:
            added.append(name)
        elif _position_changed(existing_by_name[name], imp):
            updated.append(name)

    for name in existing_by_name:
        if name not in imported_by_name:
            removed.append(name)

    return {"added": added, "updated": updated, "removed": removed}


def _position_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Check if any numeric or string field differs (excluding id)."""
    for key, new_value in new.items():
        if key == "id":
            continue
        old_value = old.get(key)
        if isinstance(new_value, (int, float)) and isinstance(old_value, (int, float)):
            if round(float(new_value), 6) != round(float(old_value), 6):
                return True
        elif new_value != old_value:
            return True
    return False


def record_change(
    history_file: str | Path,
    change_type: str,
    account: str,
    delta: dict[str, list[str]],
    summary: dict[str, Any] | None,
    previous_snapshot: dict[str, Any] | None = None,
) -> None:
    """Append a change record to the history file."""
    record = {
        "timestamp": datetime.now(CHINA_TZ).isoformat(),
        "type": change_type,
        "account": account,
        "changes": {
            "added": delta.get("added", []),
            "updated": delta.get("updated", []),
            "removed": delta.get("removed", []),
            "summary": summary or {},
        },
    }
    if previous_snapshot is not None:
        record["previous_snapshot"] = previous_snapshot

    target = Path(history_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history(history_file: str | Path, limit: int = 50) -> list[dict[str, Any]]:
    """Read the most recent N history records (newest first)."""
    if limit <= 0:
        return []
    target = Path(history_file)
    if not target.exists():
        return []

    records: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return list(reversed(records[-limit:]))


def rollback(history_file: str | Path) -> dict[str, Any] | None:
    """Restore the portfolio snapshot from the most recent history record."""
    history = read_history(history_file, limit=1)
    if not history:
        return None
    return history[0].get("previous_snapshot")
