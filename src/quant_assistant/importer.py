from __future__ import annotations

import re
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


def parse_ocr_positions(text: str) -> pd.DataFrame:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        name = _name_from_line(line)
        numbers = _numbers_from_line(line)

        if name and numbers:
            rows.append(_position_row(name, numbers, line))
        elif name and index + 1 < len(lines):
            next_numbers = _numbers_from_line(lines[index + 1])
            if next_numbers:
                rows.append(_position_row(name, next_numbers, f"{line} {lines[index + 1]}"))
                index += 1
        index += 1

    return pd.DataFrame(rows, columns=PORTFOLIO_COLUMNS)


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


def _name_from_line(line: str) -> str | None:
    cleaned = re.sub(r"[：:|,，]+", " ", line).strip()
    tokens = cleaned.split()
    if not tokens:
        return None

    name_parts = []
    for token in tokens:
        if _numbers_from_line(token):
            break
        if re.search(r"[\u4e00-\u9fffA-Za-z]", token):
            name_parts.append(token)
    name = "".join(name_parts).strip()
    if not name or name in {"名称", "持仓", "市值", "现价", "成本", "持仓盈亏", "今日盈亏"}:
        return None
    return name[:40]


def _numbers_from_line(line: str) -> list[float]:
    values = []
    for match in re.finditer(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?", line):
        raw = match.group(0).replace(",", "").replace("%", "")
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _position_row(name: str, numbers: list[float], source: str) -> dict[str, Any]:
    row = {column: None for column in PORTFOLIO_COLUMNS}
    row["name"] = name
    row["tag"] = _infer_tag(name)
    row["market_value"] = numbers[0] if numbers else None

    if len(numbers) >= 2 and _looks_like_shares(source):
        row["shares"] = numbers[1]
    if len(numbers) >= 3 and _looks_like_price_cost(source):
        row["price"] = numbers[2]
    if len(numbers) >= 4 and _looks_like_price_cost(source):
        row["cost"] = numbers[3]

    percent_values = re.findall(r"[-+]?\d+(?:\.\d+)?%", source)
    if percent_values:
        row["holding_pnl_pct"] = float(percent_values[-1].replace("%", ""))
    elif len(numbers) >= 2 and abs(numbers[-1]) <= 100:
        row["holding_pnl_pct"] = numbers[-1]
    return row


def _infer_tag(name: str) -> str:
    rules = [
        ("wide_index", ["中证500", "A500", "沪深300", "宽基", "标普500"]),
        ("tactical_ai", ["人工智能", "AI"]),
        ("power_grid", ["电网"]),
        ("military", ["军工"]),
        ("semiconductor", ["半导体", "芯片"]),
        ("robot", ["机器人"]),
    ]
    for tag, keywords in rules:
        if any(keyword in name for keyword in keywords):
            return tag
    return "imported"


def _looks_like_shares(source: str) -> bool:
    return any(keyword in source for keyword in ["持股", "股", "可卖", "份额", "数量"])


def _looks_like_price_cost(source: str) -> bool:
    return any(keyword in source for keyword in ["现价", "成本", "价格"])
