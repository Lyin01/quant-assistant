from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache

MACRO_CACHE_KEY = "macro_indicators"
AKSHARE_MACRO_ENABLED_ENV = "QA_ENABLE_AKSHARE_MACRO"
FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _safe_float(value: object) -> float | None:
    if value in (None, "-", ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _fetch_akshare_indicator(fetcher: str, column: str | None = None) -> tuple[float | None, str]:
    try:
        if not _akshare_macro_enabled():
            return None, f"AkShare macro disabled; set {AKSHARE_MACRO_ENABLED_ENV}=1 to enable."
        import akshare as ak
        fn = getattr(ak, fetcher)
        df = fn()
        if df is None or df.empty:
            return None, f"{fetcher}: empty response"
        val = df.iloc[-1]
        if column and column in df.columns:
            val = val[column]
        return _safe_float(val), f"{fetcher}: ok"
    except Exception as exc:
        return None, f"{fetcher}: {exc}"


def fetch_macro_indicators() -> tuple[dict[str, Any], list[str]]:
    cached = load_generic_cache(MACRO_CACHE_KEY)
    if cached is not None:
        return cached, ["Macro: cache hit"]

    indicators: dict[str, Any] = {}
    messages: list[str] = []

    if not _akshare_macro_enabled():
        messages.append(f"AkShare macro disabled; set {AKSHARE_MACRO_ENABLED_ENV}=1 to enable.")
    else:
        akshare_data, akshare_messages = _fetch_akshare_macro_indicators()
        indicators.update(akshare_data)
        messages.extend(akshare_messages)

    fallback_data, fallback_messages = _fetch_public_macro_fallback()
    for key, value in fallback_data.items():
        if indicators.get(key) is None and value is not None:
            indicators[key] = value
    messages.extend(fallback_messages)

    if indicators:
        save_generic_cache(MACRO_CACHE_KEY, indicators)
    return indicators, messages


def _fetch_akshare_macro_indicators() -> tuple[dict[str, Any], list[str]]:
    try:
        import akshare as ak
    except Exception as exc:
        return {}, [f"AkShare macro import failed: {exc}"]

    indicators: dict[str, Any] = {}
    messages: list[str] = []

    # China & US 10Y bond yields via akshare
    try:
        bond_df = ak.bond_zh_us_rate()
        if bond_df is not None and not bond_df.empty:
            last = bond_df.iloc[-1]
            if "中国国债收益率10年" in bond_df.columns:
                indicators["cn_10y_bond"] = _safe_float(last["中国国债收益率10年"])
            if "美国国债收益率10年" in bond_df.columns:
                indicators["us_10y_bond"] = _safe_float(last["美国国债收益率10年"])
            messages.append("bond_zh_us_rate: ok")
        else:
            messages.append("bond_zh_us_rate: empty")
    except Exception as exc:
        messages.append(f"bond_zh_us_rate: {exc}")

    # USDCNY spot
    val, msg = _fetch_akshare_indicator("currency_boc_safe", "现汇买入价")
    if val is not None:
        indicators["usdcny"] = val
    messages.append(msg)

    # China PMI
    val, msg = _fetch_akshare_indicator("macro_china_pmi")
    if val is not None:
        indicators["cn_pmi"] = val
    messages.append(msg)

    # China CPI YoY
    try:
        cpi_df = ak.macro_china_cpi()
        if cpi_df is not None and not cpi_df.empty:
            indicators["cn_cpi_yoy"] = _safe_float(cpi_df.iloc[-1].get("今值"))
            messages.append("macro_china_cpi: ok")
        else:
            messages.append("macro_china_cpi: empty")
    except Exception as exc:
        messages.append(f"macro_china_cpi: {exc}")

    # US CPI YoY
    try:
        cpi_df = ak.macro_usa_cpi()
        if cpi_df is not None and not cpi_df.empty:
            indicators["us_cpi_yoy"] = _safe_float(cpi_df.iloc[-1].get("今值"))
            messages.append("macro_usa_cpi: ok")
        else:
            messages.append("macro_usa_cpi: empty")
    except Exception as exc:
        messages.append(f"macro_usa_cpi: {exc}")

    # Fed rate
    val, msg = _fetch_akshare_indicator("macro_usa_interest_rate")
    if val is not None:
        indicators["fed_rate"] = val
    messages.append(msg)

    # Derived
    if "cn_10y_bond" in indicators and "us_10y_bond" in indicators:
        cn = indicators["cn_10y_bond"]
        us = indicators["us_10y_bond"]
        if cn is not None and us is not None:
            indicators["cn_us_spread"] = round(cn - us, 2)

    return indicators, messages


def _fetch_public_macro_fallback() -> tuple[dict[str, Any], list[str]]:
    indicators: dict[str, Any] = {}
    messages: list[str] = []

    us_10y, msg = _fetch_yahoo_latest("^TNX")
    messages.append(msg)
    if us_10y is None:
        us_10y, msg = _fetch_fred_latest("DGS10")
        messages.append(msg)
    if us_10y is not None:
        indicators["us_10y_bond"] = us_10y

    fed_rate, msg = _fetch_fred_latest("FEDFUNDS")
    if fed_rate is not None:
        indicators["fed_rate"] = fed_rate
    messages.append(msg)

    us_cpi_yoy, msg = _fetch_fred_yoy("CPIAUCSL")
    if us_cpi_yoy is not None:
        indicators["us_cpi_yoy"] = us_cpi_yoy
    messages.append(msg)

    usdcny, msg = _fetch_yahoo_latest("USDCNY=X")
    if usdcny is not None:
        indicators["usdcny"] = usdcny
    messages.append(msg)

    if not indicators:
        messages.append("Public macro fallback returned no usable data.")
    return indicators, messages


def _fetch_fred_latest(series_id: str) -> tuple[float | None, str]:
    try:
        rows = _fetch_fred_rows(series_id)
    except Exception as exc:
        return None, f"FRED {series_id}: {exc}"

    for row in reversed(rows):
        value = _safe_float(row.get(series_id))
        if value is not None:
            return value, f"FRED {series_id}: ok"
    return None, f"FRED {series_id}: no numeric data"


def _fetch_fred_yoy(series_id: str) -> tuple[float | None, str]:
    try:
        rows = _fetch_fred_rows(series_id)
    except Exception as exc:
        return None, f"FRED {series_id} YoY: {exc}"

    values = [_safe_float(row.get(series_id)) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    if len(values) < 13:
        return None, f"FRED {series_id} YoY: insufficient data"

    current = values[-1]
    previous_year = values[-13]
    return round((current / previous_year - 1) * 100, 2), f"FRED {series_id} YoY: ok"


def _fetch_fred_rows(series_id: str) -> list[dict[str, str]]:
    url = FRED_GRAPH_URL + "?" + urllib.parse.urlencode({"id": series_id})
    text = _read_url_text(url, referer="https://fred.stlouisfed.org/")
    return list(csv.DictReader(io.StringIO(text)))


def _fetch_yahoo_latest(symbol: str) -> tuple[float | None, str]:
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = YAHOO_CHART_URL.format(symbol=encoded_symbol) + "?" + urllib.parse.urlencode({"range": "5d", "interval": "1d"})
    try:
        payload = json.loads(_read_url_text(url, referer="https://finance.yahoo.com/"))
        result = ((payload.get("chart") or {}).get("result") or [{}])[0]
        quotes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        for close in reversed(quotes):
            value = _safe_float(close)
            if value is not None:
                return value, f"Yahoo {symbol}: ok"
    except Exception as exc:
        return None, f"Yahoo {symbol}: {exc}"
    return None, f"Yahoo {symbol}: no numeric data"


def _read_url_text(url: str, referer: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def _akshare_macro_enabled() -> bool:
    value = os.environ.get(AKSHARE_MACRO_ENABLED_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def macro_summary(indicators: dict[str, Any]) -> list[dict[str, str]]:
    """Generate human-readable macro summary."""
    summaries = []

    pmi = indicators.get("cn_pmi")
    if pmi is not None:
        if pmi > 50:
            summaries.append({"指标": "制造业PMI", "状态": "扩张", "解读": f"{pmi:.1f}，经济景气"})
        else:
            summaries.append({"指标": "制造业PMI", "状态": "收缩", "解读": f"{pmi:.1f}，经济承压"})

    spread = indicators.get("cn_us_spread")
    if spread is not None:
        if spread > 0:
            summaries.append({"指标": "中美利差", "状态": "中国高", "解读": f"+{spread:.2f}%，人民币资产有吸引力"})
        else:
            summaries.append({"指标": "中美利差", "状态": "美国高", "解读": f"{spread:.2f}%，资本外流压力"})

    usdcny = indicators.get("usdcny")
    if usdcny is not None:
        summaries.append({"指标": "美元兑人民币", "状态": "观察", "解读": f"{usdcny:.4f}，贬值利好出口、利空进口"})

    fed = indicators.get("fed_rate")
    if fed is not None:
        summaries.append({"指标": "美联储利率", "状态": "紧缩" if fed > 3 else "宽松", "解读": f"{fed:.2f}%，{'全球流动性承压' if fed > 3 else '利好风险资产'}"})

    cn_cpi = indicators.get("cn_cpi_yoy")
    if cn_cpi is not None:
        if cn_cpi < 1:
            summaries.append({"指标": "中国CPI", "状态": "通缩风险", "解读": f"{cn_cpi:.2f}%，需求偏弱"})
        elif cn_cpi > 3:
            summaries.append({"指标": "中国CPI", "状态": "通胀", "解读": f"{cn_cpi:.2f}%，央行可能收紧"})
        else:
            summaries.append({"指标": "中国CPI", "状态": "温和", "解读": f"{cn_cpi:.2f}%，物价平稳"})

    return summaries
