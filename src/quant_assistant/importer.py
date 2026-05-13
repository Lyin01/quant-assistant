from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


PORTFOLIO_COLUMNS = [
    "name",
    "tag",
    "market_value",
    "holding_pnl",
    "holding_pnl_pct",
    "shares",
    "price",
    "cost",
    "market_proxy",
    "last_daily_pct",
]


def read_uploaded_table(file_name: str, content: bytes) -> pd.DataFrame:
    lower = file_name.lower()
    buffer = BytesIO(content)
    if lower.endswith(".csv"):
        return pd.read_csv(buffer)
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return pd.read_excel(buffer)
    raise ValueError("只支持 CSV / Excel 表格。")


def normalize_import_table(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    normalized = pd.DataFrame()
    for target, source in mapping.items():
        if source and source in frame.columns:
            normalized[target] = frame[source]

    for column in PORTFOLIO_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None

    for column in ["market_value", "holding_pnl", "holding_pnl_pct", "shares", "price", "cost", "last_daily_pct"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized[PORTFOLIO_COLUMNS]
    return normalized


def dataframe_to_positions(frame: pd.DataFrame) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        name = row.get("name")
        if pd.isna(name) or not str(name).strip():
            continue

        position: dict[str, Any] = {
            "id": _position_id(name, index),
            "name": str(name).strip(),
            "tag": _clean(row.get("tag")) or "imported",
        }
        for column in PORTFOLIO_COLUMNS:
            if column in {"name", "tag"}:
                continue
            value = row.get(column)
            if pd.isna(value):
                continue
            if column in {"market_proxy"}:
                position[column] = str(value).strip()
            else:
                position[column] = float(value)
        positions.append(position)
    return positions


def template_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": "示例：易方达中证500",
                "tag": "wide_index",
                "market_value": 5000,
                "holding_pnl": 100,
                "holding_pnl_pct": 2.0,
                "shares": None,
                "price": None,
                "cost": None,
                "market_proxy": "中证500",
                "last_daily_pct": -0.5,
            }
        ],
        columns=PORTFOLIO_COLUMNS,
    )


def _position_id(name: object, index: int) -> str:
    safe = "".join(character.lower() if character.isalnum() else "_" for character in str(name))
    return f"imported_{index}_{safe}".strip("_")


def _clean(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
