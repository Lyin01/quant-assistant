from __future__ import annotations

import concurrent.futures
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .disk_cache import load_cached, save_cached
from .etf_universe import FALLBACK_ETF_UNIVERSE, etf_secid


AKSHARE_MARKET_DATA_ENABLED_ENV = "QA_ENABLE_AKSHARE_MARKET_DATA"


def instrument_options(config: dict[str, Any]) -> dict[str, str]:
    quotes = _mapping(config.get("quotes"))
    options: dict[str, str] = {}
    options.update(_mapping(quotes.get("market")))
    options.update(_mapping(quotes.get("proxies")))
    return options


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def fetch_history(
    secid: str,
    start: date,
    end: date,
    adjust: str = "qfq",
) -> tuple[pd.DataFrame, list[str]]:
    # Try cache first
    start_iso = start.isoformat()
    end_iso = end.isoformat()
    cached = load_cached(secid, start_iso, end_iso, adjust)
    if cached is not None:
        return cached, ["Cache hit"]

    messages: list[str] = []

    # Try EastMoney first (faster, no heavy imports)
    try:
        frame = _fetch_eastmoney_history(secid, start, end, adjust)
        if not frame.empty:
            messages.append(f"EastMoney history: {secid}, {len(frame)} rows.")
            save_cached(secid, start_iso, end_iso, adjust, frame)
            return frame, messages
    except Exception as exc:
        messages.append(f"EastMoney history failed for {secid}: {exc}")

    try:
        frame = _fetch_tencent_history(secid, start, end, adjust)
    except Exception as exc:
        messages.append(f"Tencent history fallback failed for {secid}: {exc}")
    else:
        messages.append(f"Tencent history fallback: {secid}, {len(frame)} rows.")
        if not frame.empty:
            save_cached(secid, start_iso, end_iso, adjust, frame)
            return frame, messages

    # Fallback to AkShare only when explicitly enabled.
    if not _akshare_market_data_enabled():
        messages.append(f"AkShare market data disabled; set {AKSHARE_MARKET_DATA_ENABLED_ENV}=1 to enable.")
        return pd.DataFrame(), messages

    try:
        import akshare as ak
    except Exception as exc:
        return _tencent_history_or_empty(secid, start, end, adjust, messages + [f"AkShare import failed: {exc}"])

    code = code_from_secid(secid)
    start_text = start.strftime("%Y%m%d")
    end_text = end.strftime("%Y%m%d")

    if _is_index_secid(secid):
        symbol = _index_symbol(secid)
        try:
            frame = ak.stock_zh_index_daily_em(symbol=symbol)
        except Exception as exc:
            messages.append(f"AkShare index history failed for {symbol}: {exc}")
            try:
                frame = ak.stock_zh_index_daily(symbol=symbol)
            except Exception as fallback_exc:
                messages.append(f"AkShare alternate index history failed for {symbol}: {fallback_exc}")
                return _tencent_history_or_empty(secid, start, end, adjust, messages)
            normalized = normalize_history(frame)
            normalized = _filter_dates(normalized, start, end)
            messages.append(f"AkShare alternate index history: {symbol}, {len(normalized)} rows.")
            if not normalized.empty:
                save_cached(secid, start_iso, end_iso, adjust, normalized)
            return normalized, messages
        normalized = normalize_history(frame)
        normalized = _filter_dates(normalized, start, end)
        messages.append(f"AkShare index history: {symbol}, {len(normalized)} rows.")
        if normalized.empty:
            return _tencent_history_or_empty(secid, start, end, adjust, messages)
        save_cached(secid, start_iso, end_iso, adjust, normalized)
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
        messages.append(f"AkShare ETF history failed for {code}: {exc}")
        return _tencent_history_or_empty(secid, start, end, adjust, messages)

    normalized = normalize_history(frame)
    messages.append(f"AkShare ETF history: {code}, {len(normalized)} rows.")
    if normalized.empty:
        return _tencent_history_or_empty(secid, start, end, adjust, messages)
    save_cached(secid, start_iso, end_iso, adjust, normalized)
    return normalized, messages


def fetch_etf_ranking(limit: int = 30) -> tuple[pd.DataFrame, list[str]]:
    # EastMoney is faster (only fetches ranked data); use it first.
    messages: list[str] = []
    try:
        frame = _fetch_eastmoney_etf_ranking(limit)
    except Exception as exc:
        messages.append(f"EastMoney ETF ranking failed: {exc}")
    else:
        if not frame.empty:
            return frame, [f"EastMoney ETF ranking: {len(frame)} rows."]
        messages.append("EastMoney ETF ranking returned no rows.")

    frame, messages = _akshare_etf_ranking_or_empty(limit, messages)
    if not frame.empty:
        return frame, messages

    return _fallback_etf_ranking(limit, messages)


def _akshare_etf_ranking_or_empty(limit: int, messages: list[str]) -> tuple[pd.DataFrame, list[str]]:
    if not _akshare_market_data_enabled():
        messages.append(f"AkShare market data disabled; set {AKSHARE_MARKET_DATA_ENABLED_ENV}=1 to enable.")
        return pd.DataFrame(), messages

    try:
        import akshare as ak
    except Exception as exc:
        messages.append(f"AkShare import failed: {exc}")
        return pd.DataFrame(), messages

    try:
        frame = ak.fund_etf_spot_em()
    except Exception as exc:
        messages.append(f"AkShare ETF ranking failed: {exc}")
        return pd.DataFrame(), messages

    if frame is None or frame.empty:
        messages.append("AkShare ETF ranking returned no rows.")
        return pd.DataFrame(), messages

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
    messages.append(f"AkShare ETF ranking: {len(ranking)} rows.")
    return ranking.head(limit).reset_index(drop=True), messages


def _fallback_etf_ranking(limit: int, messages: list[str]) -> tuple[pd.DataFrame, list[str]]:
    selected = FALLBACK_ETF_UNIVERSE[: max(1, min(limit, len(FALLBACK_ETF_UNIVERSE)))]
    rows: list[dict[str, Any]] = []
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(selected))) as executor:
        futures = {
            executor.submit(_fallback_etf_snapshot, code, name, index): code
            for index, (code, name) in enumerate(selected)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                row = future.result(timeout=15)
            except Exception:
                failures += 1
                continue
            rows.append(row)

    if not rows:
        messages.append("Fallback ETF ranking returned no rows.")
        return pd.DataFrame(), messages

    ranking = pd.DataFrame(rows)
    for column in ["price", "pct", "amount", "volume", "_source_order"]:
        if column in ranking.columns:
            ranking[column] = pd.to_numeric(ranking[column], errors="coerce")
    if "pct" in ranking.columns and ranking["pct"].notna().any():
        ranking = ranking.sort_values(["pct", "_source_order"], ascending=[False, True], na_position="last")
    else:
        ranking = ranking.sort_values("_source_order")
    ranking = ranking.drop(columns=["_source_order"], errors="ignore").reset_index(drop=True)
    messages.append(f"Fallback ETF universe ranking: {len(ranking)} rows.")
    if failures:
        messages.append(f"Fallback ETF ranking skipped {failures} ETF(s) after data-source errors.")
    return ranking.head(limit), messages


def _fallback_etf_snapshot(code: str, name: str, source_order: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": code,
        "name": name,
        "price": None,
        "pct": None,
        "volume": None,
        "amount": float(len(FALLBACK_ETF_UNIVERSE) - source_order),
        "_source_order": source_order,
    }
    end = date.today()
    start = end - timedelta(days=20)
    try:
        history, _messages = fetch_history(etf_secid(code), start, end, "qfq")
    except Exception:
        return row
    if history.empty:
        return row

    latest = history.iloc[-1]
    price = _safe_number(latest.get("close"))
    pct = _safe_number(latest.get("pct"))
    if pct is None and len(history) >= 2:
        previous_close = _safe_number(history.iloc[-2].get("close"))
        if price is not None and previous_close is not None and previous_close > 0:
            pct = (price / previous_close - 1) * 100

    row["price"] = price
    row["pct"] = pct
    row["volume"] = _safe_number(latest.get("volume"))
    amount = _safe_number(latest.get("amount"))
    if amount is not None:
        row["amount"] = amount
    return row


def _safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _akshare_market_data_enabled() -> bool:
    value = os.environ.get(AKSHARE_MARKET_DATA_ENABLED_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _eastmoney_history_or_empty(
    secid: str,
    start: date,
    end: date,
    adjust: str,
    messages: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    try:
        frame = _fetch_eastmoney_history(secid, start, end, adjust)
    except Exception as exc:
        messages.append(f"EastMoney history fallback failed for {secid}: {exc}")
    else:
        messages.append(f"EastMoney history fallback: {secid}, {len(frame)} rows.")
        if not frame.empty:
            return frame, messages

    return _tencent_history_or_empty(secid, start, end, adjust, messages)


def _tencent_history_or_empty(
    secid: str,
    start: date,
    end: date,
    adjust: str,
    messages: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    try:
        frame = _fetch_tencent_history(secid, start, end, adjust)
    except Exception as exc:
        messages.append(f"Tencent history fallback failed for {secid}: {exc}")
        return pd.DataFrame(), messages

    messages.append(f"Tencent history fallback: {secid}, {len(frame)} rows.")
    return frame, messages


def _fetch_eastmoney_history(secid: str, start: date, end: date, adjust: str) -> pd.DataFrame:
    fqt = {"": "0", "qfq": "1", "hfq": "2"}.get(adjust, "1")
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": fqt,
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "lmt": "100000",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = (payload.get("data") or {}).get("klines") or []
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "pct"])

    parsed_rows = []
    for row in rows:
        fields = str(row).split(",")
        if len(fields) < 9:
            continue
        try:
            parsed_rows.append(
                {
                    "date": fields[0],
                    "open": fields[1],
                    "close": fields[2],
                    "high": fields[3],
                    "low": fields[4],
                    "volume": fields[5],
                    "amount": fields[6],
                    "pct": fields[8],
                }
            )
        except IndexError:
            continue
    return normalize_history(pd.DataFrame(parsed_rows))


def _fetch_tencent_history(secid: str, start: date, end: date, adjust: str) -> pd.DataFrame:
    symbol = _tencent_symbol(secid)
    adjustment = adjust if adjust in {"qfq", "hfq"} else "qfq"
    days = max(120, min(2000, int((end - start).days * 1.8) + 30))
    params = {"param": f"{symbol},day,,,{days},{adjustment}"}
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Referer": "https://gu.qq.com/",
            "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    data = (payload.get("data") or {}).get(symbol) or {}
    rows = data.get(f"{adjustment}day") or data.get("day") or data.get("hfqday") or data.get("qfqday") or []
    parsed_rows = []
    for row in rows:
        if len(row) < 6:
            continue
        parsed_rows.append(
            {
                "date": row[0],
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
            }
        )
    return _filter_dates(normalize_history(pd.DataFrame(parsed_rows)), start, end)


def _fetch_eastmoney_etf_ranking(limit: int) -> pd.DataFrame:
    params = {
        "pn": "1",
        "pz": str(max(limit, 20)),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
        "fields": "f12,f14,f2,f3,f5,f6",
    }
    url = "https://push2.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = (payload.get("data") or {}).get("diff") or []
    ranking = pd.DataFrame(
        [
            {
                "code": row.get("f12"),
                "name": row.get("f14"),
                "price": row.get("f2"),
                "pct": row.get("f3"),
                "volume": row.get("f5"),
                "amount": row.get("f6"),
            }
            for row in rows
        ]
    )
    if ranking.empty:
        return ranking

    for column in ["price", "pct", "volume", "amount"]:
        ranking[column] = pd.to_numeric(ranking[column], errors="coerce")
    return ranking.sort_values("pct", ascending=False).head(limit).reset_index(drop=True)


def _tencent_symbol(secid: str) -> str:
    market, _dot, code = secid.partition(".")
    prefix = "sz" if market == "0" else "sh"
    return f"{prefix}{code_from_secid(code or secid)}"
