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

SUMMARY_COLUMNS = [
    "account_type",
    "total_assets",
    "today_pnl",
    "holding_pnl",
    "market_value",
    "available_cash",
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


def parse_ocr_summary(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {column: None for column in SUMMARY_COLUMNS}
    lowered = text.lower()
    if "股票/基金" in text or "国信证券" in text or "总市值" in text or "可用" in text:
        summary["account_type"] = "stock"
    elif "支付宝" in text or "基金" in text or "账户资产" in text:
        summary["account_type"] = "fund"

    patterns = {
        "total_assets": ["总资产", "账户资产", "基金资产", "股票资产"],
        "today_pnl": ["今日盈亏", "当日收益", "场内穿透"],
        "holding_pnl": ["持仓盈亏", "持有收益"],
        "market_value": ["总市值"],
        "available_cash": ["可用", "股票可用"],
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for target, keywords in patterns.items():
            if any(keyword in line for keyword in keywords):
                numbers = _numbers_from_line(line)
                if numbers:
                    summary[target] = numbers[-1]
    return summary


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
        if _is_numeric_token(token):
            break
        if re.search(r"[\u4e00-\u9fffA-Za-z]", token):
            name_parts.append(token)
    name = "".join(name_parts).strip()
    summary_names = {
        "名称",
        "持仓",
        "市值",
        "现价",
        "成本",
        "账户资产",
        "基金资产",
        "股票资产",
        "总资产",
        "总资产元",
        "今日盈亏",
        "当日收益",
        "场内穿透",
        "持仓盈亏",
        "持有收益",
        "总市值",
        "可用",
    }
    if not name or name in summary_names:
        return None
    return name[:40]


def _is_numeric_token(token: str) -> bool:
    cleaned = token.replace(",", "").replace("%", "").strip()
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned))


def _numbers_from_line(line: str) -> list[float]:
    values = []
    number_pattern = r"(?<![A-Za-z0-9_\u4e00-\u9fff])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9_\u4e00-\u9fff])"
    for match in re.finditer(number_pattern, line):
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

    percent_values = re.findall(r"[-+]?\d+(?:\.\d+)?%", source)
    if len(numbers) >= 7:
        row["shares"] = numbers[1]
        row["price"] = numbers[3]
        row["cost"] = numbers[4]
        row["holding_pnl"] = numbers[-2]
    elif len(numbers) == 6:
        row["shares"] = numbers[1]
        row["price"] = numbers[2]
        row["cost"] = numbers[3]
        row["holding_pnl"] = numbers[4]
    elif len(numbers) == 5:
        row["shares"] = numbers[1]
        row["price"] = numbers[2]
        row["holding_pnl"] = numbers[-2]
    elif len(numbers) == 4 and len(percent_values) >= 2:
        row["last_daily_pct"] = numbers[1]
        row["holding_pnl"] = numbers[2]
    elif len(numbers) == 3 and percent_values:
        row["holding_pnl"] = numbers[1]

    if len(numbers) >= 2 and _looks_like_shares(source):
        row["shares"] = numbers[1]
    if len(numbers) >= 3 and _looks_like_price_cost(source):
        row["price"] = numbers[2]
    if len(numbers) >= 4 and _looks_like_price_cost(source):
        row["cost"] = numbers[3]

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


def ocr_image(image_bytes: bytes) -> str:
    """Run RapidOCR on raw image bytes, return recognized text as a single string."""
    from rapidocr_onnxruntime import RapidOCR

    import numpy as np
    from PIL import Image

    engine = RapidOCR()
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    result, _ = engine(np.array(img))
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def merge_positions(
    existing_positions: list[dict[str, Any]],
    imported_positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge imported positions into existing ones (additive). Updates matching names, preserves unmatched."""
    imported_by_name: dict[str, dict[str, Any]] = {}
    for pos in imported_positions:
        imported_by_name[pos.get("name", "")] = pos

    merged: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for existing in existing_positions:
        name = existing.get("name", "")
        imp = imported_by_name.get(name)
        if imp:
            updated = dict(imp)
            for field in ("id", "tag", "market_proxy"):
                if field in existing and existing[field]:
                    updated[field] = existing[field]
            merged.append(updated)
            used_names.add(name)
        else:
            merged.append(existing)

    for imp in imported_positions:
        name = imp.get("name", "")
        if name not in used_names:
            if not imp.get("tag") or imp["tag"] == "imported":
                imp["tag"] = _infer_tag(name)
            merged.append(imp)

    return merged


def merge_account_summary(
    existing_account: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Update account-level fields from parsed summary, keeping existing as fallback."""
    updated = dict(existing_account)
    for summary_key in ("total_assets", "today_pnl", "holding_pnl", "market_value", "available_cash"):
        value = summary.get(summary_key)
        if value is not None:
            updated[summary_key] = value
    return updated
