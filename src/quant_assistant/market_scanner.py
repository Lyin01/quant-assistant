from __future__ import annotations

import concurrent.futures
import json
import time
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache
from .market_data import normalize_history

DEFAULT_SCAN_LIMIT = 30
SUMMARY_CACHE_PREFIX = "scanner_summary_v1"


def fetch_all_etfs() -> pd.DataFrame:
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
            ]
        )
        for col in ["price", "pct", "volume", "amount", "total_mv", "float_mv"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["code", "name"])
        if not df.empty:
            return df
    except Exception:
        pass

    # Fallback to AkShare
    try:
        import akshare as ak
        frame = ak.fund_etf_spot_em()
        if frame is None or frame.empty:
            return pd.DataFrame()
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
        for col in ["price", "pct", "volume", "amount", "total_mv", "float_mv"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["code", "name"])
        return df
    except Exception:
        return pd.DataFrame()


def _etf_secid(code: str) -> str:
    if code.startswith("5") or code.startswith("1"):
        return f"1.{code}"
    return f"0.{code}"


def _fetch_eastmoney_klines(secid: str, days: int = 60) -> pd.DataFrame:
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=days + 20)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
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


def _scan_one(code: str, name: str, price: float) -> dict[str, Any] | None:
    cache_key = f"scanner_{code}"
    cached = load_generic_cache(cache_key)
    if cached is not None:
        cached["from_cache"] = True
        return cached

    secid = _etf_secid(code)
    try:
        klines = _fetch_eastmoney_klines(secid, days=70)
    except Exception:
        return None

    factors = compute_factors(klines)
    if not factors:
        return None

    score = _score(factors, price)
    result = {
        "code": code,
        "name": name,
        "price": price,
        "score": score,
        **factors,
    }
    save_generic_cache(cache_key, result)
    return result


def scan_etfs(top_n: int = DEFAULT_SCAN_LIMIT, max_workers: int = 8) -> tuple[pd.DataFrame, list[str]]:
    messages: list[str] = []
    start = time.perf_counter()
    summary_cache_key = f"{SUMMARY_CACHE_PREFIX}_{top_n}"
    cached_summary = load_generic_cache(summary_cache_key)
    if isinstance(cached_summary, list) and cached_summary:
        return pd.DataFrame(cached_summary), [f"Scanner summary cache hit: {len(cached_summary)} rows."]

    try:
        etfs = fetch_all_etfs()
        messages.append(f"Fetched {len(etfs)} ETFs.")
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to fetch ETF list: {exc}"]

    # Sort by turnover amount, take top N
    etfs = etfs.sort_values("amount", ascending=False).head(top_n).reset_index(drop=True)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_one, row["code"], row["name"], row["price"]): row["code"]
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
    messages.append(f"Scanned {len(results)} ETFs in {elapsed:.1f}s.")

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
    save_generic_cache(summary_cache_key, json.loads(df.to_json(orient="records", force_ascii=False)))
    return df, messages
