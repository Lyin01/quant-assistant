from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def instrument_options(config: dict[str, Any]) -> dict[str, str]:
    quotes = config.get("quotes", {})
    options: dict[str, str] = {}
    options.update(quotes.get("market", {}))
    options.update(quotes.get("proxies", {}))
    return options


def fetch_history(
    secid: str,
    start: date,
    end: date,
    adjust: str = "qfq",
) -> tuple[pd.DataFrame, list[str]]:
    try:
        import akshare as ak
    except Exception as exc:
        return pd.DataFrame(), [f"AkShare import failed: {exc}"]

    code = code_from_secid(secid)
    start_text = start.strftime("%Y%m%d")
    end_text = end.strftime("%Y%m%d")
    messages: list[str] = []

    if _is_index_secid(secid):
        symbol = _index_symbol(secid)
        try:
            frame = ak.stock_zh_index_daily_em(symbol=symbol)
        except Exception as exc:
            return pd.DataFrame(), [f"AkShare index history failed for {symbol}: {exc}"]
        normalized = normalize_history(frame)
        normalized = _filter_dates(normalized, start, end)
        messages.append(f"AkShare index history: {symbol}, {len(normalized)} rows.")
        return normalized, messages

    try:
        frame = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=start_text,
            end_date=end_text,
            adjust=adjust,
        )
    except Exception as exc:
        return pd.DataFrame(), [f"AkShare ETF history failed for {code}: {exc}"]

    normalized = normalize_history(frame)
    messages.append(f"AkShare ETF history: {code}, {len(normalized)} rows.")
    return normalized, messages


def fetch_etf_ranking(limit: int = 30) -> tuple[pd.DataFrame, list[str]]:
    try:
        import akshare as ak
    except Exception as exc:
        return pd.DataFrame(), [f"AkShare import failed: {exc}"]

    try:
        frame = ak.fund_etf_spot_em()
    except Exception as exc:
        return pd.DataFrame(), [f"AkShare ETF ranking failed: {exc}"]

    if frame is None or frame.empty:
        return pd.DataFrame(), ["AkShare ETF ranking returned no rows."]

    columns = {
        "代码": "code",
        "名称": "name",
        "最新价": "price",
        "涨跌幅": "pct",
        "成交额": "amount",
        "成交量": "volume",
    }
    existing = {source: target for source, target in columns.items() if source in frame.columns}
    ranking = frame.rename(columns=existing)
    keep = [column for column in ["code", "name", "price", "pct", "amount", "volume"] if column in ranking.columns]
    ranking = ranking[keep].copy()
    if "pct" in ranking.columns:
        ranking["pct"] = pd.to_numeric(ranking["pct"], errors="coerce")
        ranking = ranking.sort_values("pct", ascending=False)
    return ranking.head(limit).reset_index(drop=True), [f"AkShare ETF ranking: {len(ranking)} rows."]


def normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "pct"])

    rename_map = {
        "日期": "date",
        "date": "date",
        "开盘": "open",
        "open": "open",
        "最高": "high",
        "high": "high",
        "最低": "low",
        "low": "low",
        "收盘": "close",
        "close": "close",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
        "涨跌幅": "pct",
        "pct_chg": "pct",
    }
    normalized = frame.rename(columns={column: rename_map.get(str(column), str(column)) for column in frame.columns})
    keep = [column for column in ["date", "open", "high", "low", "close", "volume", "amount", "pct"] if column in normalized.columns]
    normalized = normalized[keep].copy()
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume", "amount", "pct"]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return normalized


def code_from_secid(secid: str) -> str:
    if "." in secid:
        secid = secid.split(".", 1)[1]
    digits = "".join(character for character in secid if character.isdigit())
    return digits[-6:].zfill(6)


def _is_index_secid(secid: str) -> bool:
    code = code_from_secid(secid)
    return code.startswith("000") or code.startswith("399")


def _index_symbol(secid: str) -> str:
    market, _dot, code = secid.partition(".")
    if market == "0":
        return f"sz{code_from_secid(code)}"
    return f"sh{code_from_secid(code)}"


def _filter_dates(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if frame.empty or "date" not in frame.columns:
        return frame
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return frame[(frame["date"] >= start_ts) & (frame["date"] <= end_ts)].reset_index(drop=True)
