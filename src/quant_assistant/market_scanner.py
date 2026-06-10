from __future__ import annotations

import concurrent.futures
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache
from .etf_universe import FALLBACK_ETF_UNIVERSE, etf_secid
from .market_data import fetch_history, normalize_history

DEFAULT_SCAN_LIMIT = 30
SUMMARY_CACHE_PREFIX = "scanner_summary_v1"
ETF_LIST_CACHE_KEY = "scanner_etf_list_v1"
AKSHARE_ETF_LIST_ENABLED_ENV = "QA_ENABLE_AKSHARE_ETF_LIST"
ETF_LIST_COLUMNS = ["code", "name", "price", "pct", "volume", "amount", "total_mv", "float_mv"]


def _empty_etf_list() -> pd.DataFrame:
    return pd.DataFrame(columns=ETF_LIST_COLUMNS)


def _normalize_etf_list(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ETF_LIST_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None
    for column in ["price", "pct", "volume", "amount", "total_mv", "float_mv"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["code"] = normalized["code"].where(normalized["code"].notna(), "").astype(str).str.strip()
    normalized["name"] = normalized["name"].where(normalized["name"].notna(), "").astype(str).str.strip()
    normalized = normalized[(normalized["code"] != "") & (normalized["name"] != "")]
    normalized = normalized.dropna(subset=["code", "name"])
    return normalized[ETF_LIST_COLUMNS]


def _fallback_etf_universe() -> pd.DataFrame:
    rows = []
    fallback_size = len(FALLBACK_ETF_UNIVERSE)
    for index, (code, name) in enumerate(FALLBACK_ETF_UNIVERSE):
        rows.append(
            {
                "code": code,
                "name": name,
                "price": None,
                "pct": None,
                "volume": None,
                "amount": fallback_size - index,
                "total_mv": None,
                "float_mv": None,
            }
        )
    return _normalize_etf_list(pd.DataFrame(rows, columns=ETF_LIST_COLUMNS))


def fetch_all_etfs() -> pd.DataFrame:
    cached = load_generic_cache(ETF_LIST_CACHE_KEY)
    if isinstance(cached, list) and cached:
        cached_df = _normalize_etf_list(pd.DataFrame(cached))
        if not cached_df.empty:
            return cached_df

    # Try EastMoney first
    try:
        params = {
            "pn": "1",
            "pz": "10000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f6",
            "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
            "fields": "f12,f14,f2,f3,f5,f6,f18,f20,f21",
        }
        url = "https://push2.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://quote.eastmoney.com/",
                "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))

        rows = (payload.get("data") or {}).get("diff") or []
        df = pd.DataFrame(
            [
                {
                    "code": row.get("f12"),
                    "name": row.get("f14"),
                    "price": row.get("f2"),
                    "pct": row.get("f3"),
                    "volume": row.get("f5"),
                    "amount": row.get("f6"),
                    "total_mv": row.get("f20"),
                    "float_mv": row.get("f21"),
                }
                for row in rows
            ],
            columns=ETF_LIST_COLUMNS,
        )
        df = _normalize_etf_list(df)
        if not df.empty:
            save_generic_cache(ETF_LIST_CACHE_KEY, json.loads(df.to_json(orient="records", force_ascii=False)))
            return df
    except Exception:
        pass

    # Fallback to AkShare only when explicitly enabled. Some AkShare data paths can
    # be slow or depend on native JS runtimes, while scan_etfs already has a local
    # fallback universe for interactive use.
    if not _akshare_etf_list_enabled():
        return _empty_etf_list()

    # Fallback to AkShare
    try:
        import akshare as ak
        frame = ak.fund_etf_spot_em()
        if frame is None or frame.empty:
            return _empty_etf_list()
        rename = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct",
            "成交量": "volume",
            "成交额": "amount",
            "总市值": "total_mv",
            "流通市值": "float_mv",
        }
        existing = {k: v for k, v in rename.items() if k in frame.columns}
        df = frame.rename(columns=existing)
        df = _normalize_etf_list(df)
        if not df.empty:
            save_generic_cache(ETF_LIST_CACHE_KEY, json.loads(df.to_json(orient="records", force_ascii=False)))
        return df
    except Exception:
        return _empty_etf_list()


def _akshare_etf_list_enabled() -> bool:
    value = os.environ.get(AKSHARE_ETF_LIST_ENABLED_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _etf_secid(code: str) -> str:
    return etf_secid(code)


def _fetch_eastmoney_klines(secid: str, days: int = 80, adjust: str = "qfq") -> pd.DataFrame:
    fqt = {"": "0", "qfq": "1", "hfq": "2"}.get(adjust, "1")
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=days + 20)
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
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = (payload.get("data") or {}).get("klines") or []
    parsed = []
    for row in rows:
        fields = str(row).split(",")
        if len(fields) < 9:
            continue
        parsed.append(
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
    return normalize_history(pd.DataFrame(parsed))


def compute_factors(klines: pd.DataFrame) -> dict[str, float]:
    if klines.empty or len(klines) < 20:
        return {}
    data = klines.sort_values("date").reset_index(drop=True)
    close = data["close"]

    ret_5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    ret_20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0
    ret_60 = (close.iloc[-1] / close.iloc[-61] - 1) * 100 if len(close) >= 61 else 0

    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20

    trend_score = 0
    if close.iloc[-1] > ma20:
        trend_score += 1
    if close.iloc[-1] > ma60:
        trend_score += 1
    if ma20 > ma60:
        trend_score += 1

    volatility = close.pct_change().rolling(20).std().iloc[-1] * 100

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_value = rsi.iloc[-1]

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line.iloc[-1] - macd_signal.iloc[-1]

    high_20 = close.rolling(20).max().iloc[-1]
    drawdown_20 = (close.iloc[-1] / high_20 - 1) * 100 if high_20 > 0 else 0

    vol_recent = data["volume"].iloc[-5:].mean()
    vol_hist = data["volume"].iloc[-20:].mean()
    vol_ratio = vol_recent / vol_hist if vol_hist > 0 else 1

    return {
        "ret_5": ret_5,
        "ret_20": ret_20,
        "ret_60": ret_60,
        "trend_score": trend_score,
        "volatility": volatility,
        "rsi": rsi_value,
        "macd_hist": macd_hist,
        "drawdown_20": drawdown_20,
        "vol_ratio": vol_ratio,
    }


def _score(factors: dict[str, float], current_price: float) -> float:
    if current_price <= 0:
        current_price = 1
    score = 0.0

    # Momentum 30%
    score += min(max(factors.get("ret_5", 0) / 5, -1), 1) * 10
    score += min(max(factors.get("ret_20", 0) / 10, -1), 1) * 10
    score += min(max(factors.get("ret_60", 0) / 20, -1), 1) * 10

    # Trend 25%
    score += factors.get("trend_score", 0) / 3 * 25

    # RSI 15% — prefer 45-65 (not extreme)
    rsi = factors.get("rsi", 50)
    if 45 <= rsi <= 65:
        score += 15
    elif 35 <= rsi < 45 or 65 < rsi <= 75:
        score += 10
    elif 25 <= rsi < 35 or 75 < rsi <= 85:
        score += 5

    # MACD 15%
    macd_hist = factors.get("macd_hist", 0)
    score += min(max(macd_hist / current_price * 100, -1), 1) * 15

    # Volume 15%
    vol_ratio = factors.get("vol_ratio", 1)
    if 1.2 <= vol_ratio <= 3:
        score += 15
    elif vol_ratio > 3:
        score += 10
    elif vol_ratio > 1:
        score += 5

    return round(score, 1)


def _tencent_symbol(code: str) -> str:
    # Shanghai: 5xxxxx / 6xxxxx; Shenzhen: 0xxxxx / 3xxxxx / 15xxxxx / 16xxxxx
    if code.startswith("5") or code.startswith("6"):
        return f"sh{code}"
    return f"sz{code}"


def _fetch_tencent_klines(code: str, days: int = 120) -> pd.DataFrame:
    symbol = _tencent_symbol(code)
    params = {"param": f"{symbol},day,,,{days},qfq"}
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
    rows = data.get("qfqday") or data.get("day") or data.get("hfqday") or []
    parsed = []
    for row in rows:
        if len(row) < 6:
            continue
        parsed.append(
            {
                "date": row[0],
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
            }
        )
    return normalize_history(pd.DataFrame(parsed))


def _coerce_price(primary: Any, fallback: Any = None) -> float:
    for value in (primary, fallback):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not pd.isna(number) and number > 0:
            return number
    return 1.0


def _latest_close(klines: pd.DataFrame) -> float | None:
    if klines.empty or "close" not in klines.columns:
        return None
    close = pd.to_numeric(klines["close"], errors="coerce").dropna()
    if close.empty:
        return None
    return float(close.iloc[-1])


def _scan_one(code: str, name: str, price: float, force_refresh: bool = False) -> dict[str, Any] | None:
    cache_key = f"scanner_{code}"
    if not force_refresh:
        cached = load_generic_cache(cache_key)
        if isinstance(cached, dict):
            cached["from_cache"] = True
            return cached

    klines = pd.DataFrame()
    # Try Tencent first — covers all on-exchange funds (ETF + LOF) and has a hard timeout
    try:
        klines = _fetch_tencent_klines(code, days=120)
    except Exception:
        pass

    # Fallback to fetch_history (cache -> EastMoney -> Tencent -> optional AkShare)
    if klines.empty or len(klines) < 20:
        secid = _etf_secid(code)
        try:
            end = date.today()
            start = end - timedelta(days=80)
            klines, _msgs = fetch_history(secid, start, end)
        except Exception:
            return None

    factors = compute_factors(klines)
    if not factors:
        return None

    scan_price = _coerce_price(price, _latest_close(klines))
    score = _score(factors, scan_price)
    result = {
        "code": code,
        "name": name,
        "price": scan_price,
        "score": score,
        "from_cache": False,
        **factors,
    }
    save_generic_cache(cache_key, result)
    return result


def scan_etfs(top_n: int = DEFAULT_SCAN_LIMIT, max_workers: int = 6, force_refresh: bool = False) -> tuple[pd.DataFrame, list[str]]:
    messages: list[str] = []
    start = time.perf_counter()
    summary_cache_key = f"{SUMMARY_CACHE_PREFIX}_{top_n}"
    if not force_refresh:
        cached_summary = load_generic_cache(summary_cache_key)
        if isinstance(cached_summary, list) and cached_summary:
            return pd.DataFrame(cached_summary), [f"Scanner summary cache hit: {len(cached_summary)} rows."]

    try:
        etfs = fetch_all_etfs()
        messages.append(f"Fetched {len(etfs)} ETFs.")
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to fetch ETF list: {exc}"]

    if etfs.empty:
        etfs = _fallback_etf_universe()
        messages.append(f"ETF list is empty — using fallback universe: {len(etfs)} ETFs.")
    if "amount" not in etfs.columns:
        messages.append("ETF list missing turnover amount, using unsorted source order.")
        etfs = etfs.copy()
        etfs["amount"] = 0

    # Sort by turnover amount, take top N
    etfs = etfs.sort_values("amount", ascending=False, na_position="last").head(top_n).reset_index(drop=True)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_one, row["code"], row["name"], row["price"], force_refresh): row["code"]
            for _, row in etfs.iterrows()
        }
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                result = future.result(timeout=10)
                if result:
                    results.append(result)
            except Exception as exc:
                messages.append(f"Scan failed for {code}: {exc}")

    elapsed = time.perf_counter() - start
    failed_count = top_n - len(results)
    messages.append(f"Scanned {len(results)}/{top_n} ETFs in {elapsed:.1f}s.")
    if failed_count > 0:
        messages.append(f"{failed_count} ETF(s) failed — data source timeout or network issue. Try '强制刷新' or check 行情源状态.")

    if not results:
        return pd.DataFrame(), messages

    df = pd.DataFrame(results)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Rename columns for display
    display_cols = {
        "rank": "排名",
        "code": "代码",
        "name": "名称",
        "price": "价格",
        "score": "综合评分",
        "ret_5": "5日涨幅%",
        "ret_20": "20日涨幅%",
        "ret_60": "60日涨幅%",
        "trend_score": "趋势分(0-3)",
        "volatility": "波动率%",
        "rsi": "RSI",
        "macd_hist": "MACD柱",
        "drawdown_20": "20日回撤%",
        "vol_ratio": "量比",
    }
    df = df.rename(columns={k: v for k, v in display_cols.items() if k in df.columns})
    # Only cache when at least half of the requested ETFs succeeded — avoids cache pollution from partial failures
    if len(results) >= top_n / 2:
        save_generic_cache(summary_cache_key, json.loads(df.to_json(orient="records", force_ascii=False)))
    else:
        messages.append(f"Only {len(results)}/{top_n} succeeded, summary not cached — re-scan will retry failed ETFs.")
    return df, messages
