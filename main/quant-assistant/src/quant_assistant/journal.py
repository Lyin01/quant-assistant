from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable


def append_recommendations(path: str | Path, recommendations: Iterable[dict[str, str]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = target.exists()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with target.open("a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["time", "action", "instrument", "amount", "reason"])
        if not exists:
            writer.writeheader()
        for rec in recommendations:
            writer.writerow(
                {
                    "time": now,
                    "action": rec.get("action", ""),
                    "instrument": rec.get("instrument", ""),
                    "amount": rec.get("amount", ""),
                    "reason": rec.get("reason", ""),
                }
            )
