from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache

MACRO_CACHE_KEY = "macro_indicators"
AKSHARE_MACRO_ENABLED_ENV = "QA_ENABLE_AKSHARE_MACRO"


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

    if not _akshare_macro_enabled():
        return {}, [f"AkShare macro disabled; set {AKSHARE_MACRO_ENABLED_ENV}=1 to enable."]

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

    save_generic_cache(MACRO_CACHE_KEY, indicators)
    return indicators, messages


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
