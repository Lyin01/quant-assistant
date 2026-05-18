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


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return False
    return True

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
    try:
        if lower.endswith(".csv"):
            return pd.read_csv(buffer)
        if lower.endswith(".xlsx") or lower.endswith(".xls"):
            return pd.read_excel(buffer)
    except Exception as exc:
        raise ValueError(f"文件解析失败（{file_name}）：{exc}") from exc
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


def parse_ocr_import_text(text: str) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    parsed = parse_ocr_positions(text)
    summary = parse_ocr_summary(text)
    positions = dataframe_to_positions(parsed)
    return parsed, summary, positions


def parse_ocr_positions(text: str) -> pd.DataFrame:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    screenshot_rows = _parse_multiline_stock_rows(lines) or _parse_multiline_fund_rows(lines)
    if screenshot_rows:
        return pd.DataFrame(screenshot_rows, columns=PORTFOLIO_COLUMNS)

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

    # 不再自动推断 account_type：
    # "总市值"/"可用" 在基金截图中也很常见（可用份额、可用金额），极易误判。
    # 账户类型交给 detect_target_account 用预设和持仓特征（是否有 shares）判断。

    patterns = {
        "total_assets": ["总资产", "账户资产", "基金资产", "股票资产"],
        "today_pnl": ["今日盈亏", "当日收益", "场内穿透"],
        "holding_pnl": ["持仓盈亏", "持有收益"],
        "market_value": ["总市值"],
        "available_cash": ["可用", "股票可用"],
    }
    pending_targets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "名称/市值" in line or "持股/可卖" in line:
            break
        numbers = _numbers_from_line(line)
        matched_targets = [
            target
            for target, keywords in patterns.items()
            if any(keyword in line for keyword in keywords)
        ]
        if matched_targets:
            if numbers:
                for target in matched_targets:
                    if summary[target] is None:
                        summary[target] = numbers[-1]
            else:
                pending_targets.extend(
                    target
                    for target in matched_targets
                    if target not in pending_targets
                    and summary[target] is None
                    and not (target == "holding_pnl" and line == "持有收益")
                )
            continue

        if pending_targets and numbers:
            target = pending_targets.pop(0)
            if summary[target] is None:
                summary[target] = numbers[-1]
            continue

        for target, keywords in patterns.items():
            if any(keyword in line for keyword in keywords):
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
    line = re.sub(r"(?<!\d)(\d{1,3})\.(\d{3})\.(\d{2})(?!\d)", r"\1,\2.\3", line)
    number_pattern = r"(?<![A-Za-z0-9_\u4e00-\u9fff])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9_\u4e00-\u9fff])"
    for match in re.finditer(number_pattern, line):
        raw = match.group(0).replace(",", "").replace("%", "")
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _number_tokens_from_line(line: str) -> list[dict[str, Any]]:
    normalized = re.sub(r"(?<!\d)(\d{1,3})\.(\d{3})\.(\d{2})(?!\d)", r"\1,\2.\3", line)
    number_pattern = r"(?<![A-Za-z0-9_\u4e00-\u9fff])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9_\u4e00-\u9fff])"
    tokens: list[dict[str, Any]] = []
    for match in re.finditer(number_pattern, normalized):
        raw = match.group(0)
        try:
            value = float(raw.replace(",", "").replace("%", ""))
        except ValueError:
            continue
        tokens.append(
            {
                "value": value,
                "raw": raw,
                "is_percent": raw.endswith("%"),
                "is_signed": raw.startswith(("+", "-")),
                "has_currency": "￥" in normalized[: match.end()],
            }
        )
    return tokens


def _clean_ocr_name(name: str) -> str:
    return name.strip().rstrip("·…").strip()


def _base_row(name: str) -> dict[str, Any]:
    cleaned_name = _clean_ocr_name(name)
    row = {column: None for column in PORTFOLIO_COLUMNS}
    row["name"] = cleaned_name
    row["tag"] = _infer_tag(cleaned_name)
    proxy = _infer_market_proxy(cleaned_name, row["tag"])
    if proxy:
        row["market_proxy"] = proxy
    return row


def _is_stock_name_line(lines: list[str], index: int) -> bool:
    name = _name_from_line(lines[index])
    if not name:
        return False
    blocked = {
        "自选",
        "行情",
        "发现",
        "去券商",
        "买入",
        "卖出",
        "撤单",
        "交易记录",
        "资金明细",
        "银证转账",
        "盈亏分析",
        "股票基金",
        "通用回购",
        "报价回购",
    }
    if name in blocked or name.startswith("证券服务由"):
        return False
    if _numbers_from_line(lines[index]):
        return False
    return index + 1 < len(lines) and bool(_numbers_from_line(lines[index + 1]))


def _parse_multiline_stock_rows(lines: list[str]) -> list[dict[str, Any]]:
    if not any("名称/市值" in line for line in lines):
        return []

    start = next((index for index, line in enumerate(lines) if "名称/市值" in line), 0) + 1
    rows: list[dict[str, Any]] = []
    index = start
    while index < len(lines):
        if not _is_stock_name_line(lines, index):
            index += 1
            continue

        name = _name_from_line(lines[index])
        group: list[dict[str, Any]] = []
        index += 1
        while index < len(lines) and not _is_stock_name_line(lines, index):
            if lines[index].startswith("证券服务由"):
                break
            group.extend(_number_tokens_from_line(lines[index]))
            index += 1

        row = _stock_row_from_tokens(str(name), group)
        if row:
            rows.append(row)

    return rows


def _stock_row_from_tokens(name: str, tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    non_percent = [token for token in tokens if not token["is_percent"]]
    percent_values = [token["value"] for token in tokens if token["is_percent"]]
    if len(non_percent) < 3:
        return None

    row = _base_row(name)

    shares_token = next(
        (
            token
            for token in non_percent
            if not token["is_signed"] and float(token["value"]).is_integer() and token["value"] > 0
        ),
        None,
    )
    if not shares_token:
        return None
    row["shares"] = shares_token["value"]

    shares_index = non_percent.index(shares_token)
    price_token = next(
        (
            token
            for token in non_percent[shares_index + 1 :]
            if "." in token["raw"] and not token["is_signed"] and 0 < token["value"] < 1000
        ),
        None,
    )
    if not price_token:
        return None
    row["price"] = price_token["value"]

    expected_market_value = row["shares"] * row["price"]
    market_candidates = [
        token
        for token in non_percent
        if token not in (shares_token, price_token) and token["value"] > 0
    ]
    if market_candidates:
        market_token = min(market_candidates, key=lambda token: abs(token["value"] - expected_market_value))
        row["market_value"] = market_token["value"]
    else:
        market_token = None

    cost_candidates = [
        token
        for token in non_percent
        if token not in (shares_token, price_token, market_token)
        and not token["is_signed"]
        and "." in token["raw"]
        and 0 < token["value"] < 1000
    ]
    if cost_candidates:
        row["cost"] = min(cost_candidates, key=lambda token: abs(token["value"] - row["price"]))["value"]

    pnl_token = next(
        (
            token
            for token in non_percent
            if token not in (shares_token, price_token, market_token)
            and token["is_signed"]
        ),
        None,
    )
    if pnl_token:
        row["holding_pnl"] = pnl_token["value"]
    if percent_values:
        row["holding_pnl_pct"] = percent_values[-1]
    return row


_FUND_NAME_PREFIXES = (
    "易方达",
    "天弘",
    "大成",
    "博时",
    "广发",
    "华宝",
    "华夏",
    "嘉实",
    "南方",
    "招商",
    "富国",
    "鹏华",
    "工银",
    "国泰",
    "汇添富",
    "景顺",
    "银华",
    "中欧",
    "兴全",
    "诺安",
    "交银",
    "建信",
    "农银",
    "长城",
    "万家",
    "平安",
)


def _is_fund_name_line(line: str) -> bool:
    name = _name_from_line(line)
    if not name or _numbers_from_line(line):
        return False
    cleaned_name = _clean_ocr_name(name)
    return any(cleaned_name.startswith(prefix) for prefix in _FUND_NAME_PREFIXES)


def _parse_multiline_fund_rows(lines: list[str]) -> list[dict[str, Any]]:
    if not any("账户资产" in line for line in lines):
        return []

    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if not _is_fund_name_line(lines[index]):
            index += 1
            continue

        name = str(_name_from_line(lines[index]))
        group: list[dict[str, Any]] = []
        index += 1
        while index < len(lines) and not _is_fund_name_line(lines[index]):
            group.extend(_number_tokens_from_line(lines[index]))
            index += 1

        row = _fund_row_from_tokens(name, group)
        if row:
            rows.append(row)

    return rows


def _fund_row_from_tokens(name: str, tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    row = _base_row(name)
    non_percent = [token for token in tokens if not token["is_percent"]]
    percent_values = [token["value"] for token in tokens if token["is_percent"]]

    market_token = next((token for token in non_percent if token["has_currency"]), None)
    if not market_token:
        positive_values = [token for token in non_percent if token["value"] > 10]
        if positive_values:
            market_token = max(positive_values, key=lambda token: token["value"])
    if not market_token:
        return None

    row["market_value"] = market_token["value"]
    pnl_token = next(
        (
            token
            for token in non_percent
            if token is not market_token and token["is_signed"]
        ),
        None,
    )
    if pnl_token:
        row["holding_pnl"] = pnl_token["value"]
    if percent_values:
        row["last_daily_pct"] = percent_values[0]
        row["holding_pnl_pct"] = percent_values[-1]
    return row


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
        ("wide_index", ["中证500", "A500", "沪深300", "宽基"]),
        ("tactical_ai", ["人工智能", "AI"]),
        ("power_grid", ["电网"]),
        ("military", ["军工"]),
        ("semiconductor", ["半导体", "芯片"]),
        ("robot", ["机器人"]),
        ("overseas", ["纳指", "纳斯达克", "标普", "标普500"]),
        ("healthcare", ["创新药", "医药"]),
        ("defensive", ["稳健", "债", "货币"]),
    ]
    for tag, keywords in rules:
        if any(keyword in name for keyword in keywords):
            return tag
    return "imported"


_TAG_TO_PROXY: dict[str, str | None] = {
    "wide_index": "中证500",
    "tactical_ai": "人工智能",
    "core_ai_dca": "人工智能",
    "power_grid": "电网设备",
    "military": "军工",
    "semiconductor": "半导体",
    "robot": "机器人",
    "overseas": None,   # 需根据持仓名称进一步推断
    "healthcare": "创新药",
    "defensive": None,
    "imported": None,
}


_PROXY_NAME_RULES = [
    ("纳指", ["纳指", "纳斯达克"]),
    ("标普500", ["标普", "标普500"]),
    ("中证500", ["中证500"]),
    ("人工智能", ["人工智能"]),
    ("电网设备", ["电网"]),
    ("军工", ["军工"]),
    ("半导体", ["半导体", "芯片"]),
    ("机器人", ["机器人"]),
    ("创新药", ["创新药", "医药"]),
]


def _infer_market_proxy(name: str, tag: str) -> str | None:
    """Infer market_proxy from position name and tag."""
    # First try name-based matching for all tags
    for proxy, keywords in _PROXY_NAME_RULES:
        if any(keyword in name for keyword in keywords):
            return proxy
    # Fallback to tag-based default
    return _TAG_TO_PROXY.get(tag)


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
            # 以现有数据为底，只覆盖导入数据中非空的字段
            updated = dict(existing)
            for field, value in imp.items():
                if _has_value(value):
                    updated[field] = value
            # id/tag/market_proxy 永远以现有为准（除非导入明确指定了有效值）
            for field in ("id", "tag", "market_proxy"):
                if field in existing and existing[field]:
                    if not imp.get(field) or imp[field] == "imported":
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
            if not imp.get("market_proxy"):
                proxy = _infer_market_proxy(name, imp.get("tag", "imported"))
                if proxy:
                    imp["market_proxy"] = proxy
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


def update_account_from_import(
    existing_account: dict[str, Any],
    imported_positions: list[dict[str, Any]],
    account_key: str,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge imported positions and refresh account totals for overview display."""
    updated = dict(existing_account)
    updated["positions"] = merge_positions(existing_account.get("positions", []), imported_positions)
    updated = recalc_account_summary(updated, account_key)
    if summary:
        updated = merge_account_summary(updated, summary)
    return updated


def recalc_account_summary(account: dict[str, Any], account_key: str = "") -> dict[str, Any]:
    """Recalculate account totals from current positions.

    Stock: total_assets = sum(market_value) + available_cash
    Fund:  total_assets = sum(market_value)
    """
    updated = dict(account)
    positions = updated.get("positions", [])
    market_value_sum = sum(
        float(p.get("market_value", 0) or 0)
        for p in positions
    )

    if account_key == "stock" or (not account_key and "available_cash" in updated):
        # Stock account
        updated["market_value"] = round(market_value_sum, 2)
        updated["total_assets"] = round(market_value_sum + float(updated.get("available_cash", 0) or 0), 2)
    else:
        # Fund account
        updated["total_assets"] = round(market_value_sum, 2)

    return updated
