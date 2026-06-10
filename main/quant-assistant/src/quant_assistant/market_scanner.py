from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache
from .market_data import fetch_history, normalize_history

DEFAULT_SCAN_LIMIT = 30
SUMMARY_CACHE_PREFIX = "scanner_summary_v4"
ETF_CACHE_PREFIX = "scanner_v4"
STOCK_CACHE_PREFIX = "stock_scanner_v3"

MARKET_UNIVERSES = {
    "etf": "ETF",
    "stock": "A股",
    "all": "ETF + A股",
}

SCAN_MODES = {
    "balanced": "均衡",
    "strict": "稳健",
    "aggressive": "进攻",
}

DEFENSIVE_ETF_KEYWORDS = (
    "货币",
    "现金",
    "添益",
    "日利",
    "收益",
    "短债",
    "中短债",
    "信用债",
    "国债",
    "政金债",
    "城投债",
    "可转债",
)

EASTMONEY_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "close",
}


def _load_eastmoney_json(url: str, timeout: int = 15) -> dict[str, Any]:
    node = _find_node_executable()
    if node:
        try:
            return _load_eastmoney_json_with_node(url, timeout=timeout, node=node)
        except Exception:
            pass

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=EASTMONEY_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    if last_error:
        raise last_error
    return {}


def _load_eastmoney_json_with_node(url: str, timeout: int = 15, node: str | None = None) -> dict[str, Any]:
    node = node or _find_node_executable()
    if not node:
        return {}
    script = """
const url = process.argv[1];
const headers = {
  Referer: "https://quote.eastmoney.com/",
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  Accept: "application/json,text/plain,*/*"
};
let lastError;
for (let attempt = 0; attempt < 3; attempt += 1) {
  try {
    const response = await fetch(url, { headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    process.stdout.write(await response.text());
    process.exit(0);
  } catch (error) {
    lastError = error;
    await new Promise((resolve) => setTimeout(resolve, 300 * (attempt + 1)));
  }
}
console.error(lastError && lastError.message ? lastError.message : String(lastError));
process.exit(1);
"""
    completed = subprocess.run(
        [node, "--input-type=module", "-e", script, url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(timeout + 5, 10),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    return json.loads(completed.stdout)


def _find_node_executable() -> str | None:
    candidates = [
        r"C:\Users\18312\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
        r"E:\cursor\resources\app\resources\helpers\node.exe",
        r"E:\python\Lib\site-packages\playwright\driver\node.exe",
        shutil.which("node"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


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
        payload = _load_eastmoney_json(url, timeout=15)

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
        df["code"] = df["code"].astype(str).str.strip()
        df = df[df["code"] != ""]
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


def fetch_all_a_shares() -> pd.DataFrame:
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
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f2,f3,f5,f6,f18,f20,f21",
        }
        url = "https://push2.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
        payload = _load_eastmoney_json(url, timeout=15)

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
        df["code"] = df["code"].astype(str).str.strip()
        df = df[df["code"].str.match(r"^(00|30|60|68)\d{4}$", na=False)]
        df = df.dropna(subset=["code", "name", "price", "amount"])
        if not df.empty:
            return df
    except Exception:
        pass

    try:
        import akshare as ak
        frame = ak.stock_zh_a_spot_em()
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
        df["code"] = df["code"].astype(str).str.strip()
        df = df[df["code"].str.match(r"^(00|30|60|68)\d{4}$", na=False)]
        return df.dropna(subset=["code", "name", "price", "amount"])
    except Exception:
        return pd.DataFrame()


def fetch_scan_universe(universe: str = "etf", include_defensive: bool = False) -> pd.DataFrame:
    cache_key = f"scanner_universe_v1_{universe}_{int(include_defensive)}"
    for attempt in range(3):
        frame = _fetch_scan_universe_once(universe, include_defensive=include_defensive)
        if not frame.empty:
            save_generic_cache(cache_key, json.loads(frame.to_json(orient="records", force_ascii=False)))
            return frame
        time.sleep(0.4 * (attempt + 1))
    cached = load_generic_cache(cache_key)
    if isinstance(cached, list) and cached:
        return pd.DataFrame(cached)
    return _cached_universe_from_scan_files(universe, include_defensive=include_defensive)


def _cached_universe_from_scan_files(universe: str, include_defensive: bool = False) -> pd.DataFrame:
    cache_dir = Path("data/cache/generic")
    if not cache_dir.exists():
        return pd.DataFrame()
    patterns = []
    if universe in {"stock", "all"}:
        patterns.append(("A股", "stock_scanner_v*.json"))
    if universe in {"etf", "all"}:
        patterns.append(("ETF", "scanner_v*.json"))

    rows: list[dict[str, Any]] = []
    for asset_type, pattern in patterns:
        for path in cache_dir.glob(pattern):
            if "summary" in path.name or "universe" in path.name:
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    item = json.load(f)
            except Exception:
                continue
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            if not code or not name:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "price": item.get("price", 0),
                    "amount": item.get("amount", 0),
                    "asset_type": asset_type,
                }
            )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates(subset=["asset_type", "code"])
    return _filter_scan_universe(frame, include_defensive=include_defensive)


def _fetch_scan_universe_once(universe: str = "etf", include_defensive: bool = False) -> pd.DataFrame:
    if universe == "stock":
        frame = fetch_all_a_shares()
        if not frame.empty:
            frame = frame.copy()
            frame["asset_type"] = "A股"
        return _filter_scan_universe(frame, include_defensive=include_defensive)
    if universe == "all":
        etfs = fetch_all_etfs()
        stocks = fetch_all_a_shares()
        frames = []
        if not etfs.empty:
            etfs = etfs.copy()
            etfs["asset_type"] = "ETF"
            frames.append(etfs)
        if not stocks.empty:
            stocks = stocks.copy()
            stocks["asset_type"] = "A股"
            frames.append(stocks)
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return _filter_scan_universe(combined, include_defensive=include_defensive)

    frame = fetch_all_etfs()
    if not frame.empty:
        frame = frame.copy()
        frame["asset_type"] = "ETF"
    return _filter_scan_universe(frame, include_defensive=include_defensive)


def _filter_scan_universe(frame: pd.DataFrame, include_defensive: bool = False) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    names = data["name"].astype(str)
    asset_types = data.get("asset_type", pd.Series("", index=data.index)).astype(str)
    stock_mask = asset_types.eq("A股")
    etf_mask = asset_types.eq("ETF")

    # ST/退市风险股不适合做普通趋势候选池。
    data = data[~(stock_mask & names.str.contains(r"ST|退", case=False, regex=True, na=False))]

    if not include_defensive:
        defensive_pattern = "|".join(DEFENSIVE_ETF_KEYWORDS)
        names = data["name"].astype(str)
        asset_types = data.get("asset_type", pd.Series("", index=data.index)).astype(str)
        data = data[~(asset_types.eq("ETF") & names.str.contains(defensive_pattern, na=False))]

    return data.reset_index(drop=True)


def _etf_secid(code: str) -> str:
    # Shanghai ETF codes start with 5 (50/51/52/56/58...); Shenzhen ETFs start with 15/16/18
    if code.startswith("5"):
        return f"1.{code}"
    return f"0.{code}"


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
    payload = _load_eastmoney_json(url, timeout=8)

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
    pct_change = close.pct_change() * 100

    ret_5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    ret_10 = (close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) >= 11 else 0
    ret_20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0
    ret_60 = (close.iloc[-1] / close.iloc[-61] - 1) * 100 if len(close) >= 61 else 0

    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
    ma20_prev = close.rolling(20).mean().iloc[-6] if len(close) >= 25 else ma20
    ma20_slope_5 = (ma20 / ma20_prev - 1) * 100 if ma20_prev and ma20_prev > 0 else 0

    trend_score = 0
    if close.iloc[-1] > ma20:
        trend_score += 1
    if close.iloc[-1] > ma60:
        trend_score += 1
    if ma20 > ma60:
        trend_score += 1
    if ma20_slope_5 > 0:
        trend_score += 1

    up_days_5 = int((pct_change.iloc[-5:] > 0).sum()) if len(close) >= 6 else 0
    up_days_10 = int((pct_change.iloc[-10:] > 0).sum()) if len(close) >= 11 else 0
    consecutive_up_days = _consecutive_positive_days(pct_change)

    volatility = close.pct_change().rolling(20).std().iloc[-1] * 100

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    loss = loss.replace(0, 1e-10)
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
    up_volume = data.loc[pct_change > 0, "volume"].iloc[-10:].mean()
    down_volume = data.loc[pct_change < 0, "volume"].iloc[-10:].mean()
    volume_confirm = 1.0 if pd.notna(up_volume) and pd.notna(down_volume) and up_volume > down_volume else 0.0

    continuation_score = _continuation_score(
        {
            "ret_5": ret_5,
            "ret_10": ret_10,
            "ret_20": ret_20,
            "trend_score": trend_score,
            "up_days_5": up_days_5,
            "up_days_10": up_days_10,
            "consecutive_up_days": consecutive_up_days,
            "ma20_slope_5": ma20_slope_5,
            "drawdown_20": drawdown_20,
            "rsi": rsi_value,
            "macd_hist": macd_hist,
            "vol_ratio": vol_ratio,
            "volume_confirm": volume_confirm,
        }
    )

    return {
        "ret_5": ret_5,
        "ret_10": ret_10,
        "ret_20": ret_20,
        "ret_60": ret_60,
        "trend_score": trend_score,
        "up_days_5": up_days_5,
        "up_days_10": up_days_10,
        "consecutive_up_days": consecutive_up_days,
        "ma20_slope_5": ma20_slope_5,
        "volatility": volatility,
        "rsi": rsi_value,
        "macd_hist": macd_hist,
        "drawdown_20": drawdown_20,
        "vol_ratio": vol_ratio,
        "volume_confirm": volume_confirm,
        "continuation_score": continuation_score,
    }


def _consecutive_positive_days(pct_change: pd.Series) -> int:
    count = 0
    for value in reversed(pct_change.dropna().tolist()):
        if value <= 0:
            break
        count += 1
    return count


def _continuation_score(factors: dict[str, float]) -> float:
    score = 0.0

    # Price structure: close above rising MA20/MA60 is the backbone of a trend.
    score += factors.get("trend_score", 0) / 4 * 25

    # Continuity: reward repeated gains, not only one-day spikes.
    score += min(factors.get("up_days_5", 0) / 4, 1) * 10
    score += min(factors.get("up_days_10", 0) / 7, 1) * 10
    score += min(factors.get("consecutive_up_days", 0) / 4, 1) * 8

    # Momentum: 5/10/20 day returns should be positive but not absurdly extended.
    score += min(max(factors.get("ret_5", 0) / 5, 0), 1) * 8
    score += min(max(factors.get("ret_10", 0) / 8, 0), 1) * 8
    score += min(max(factors.get("ret_20", 0) / 12, 0), 1) * 7

    # Position risk: small pullbacks near recent highs are healthier than vertical chasing.
    drawdown = factors.get("drawdown_20", 0)
    if -6 <= drawdown <= -1:
        score += 8
    elif -1 < drawdown <= 0:
        score += 5
    elif -10 <= drawdown < -6:
        score += 3

    # Confirmation: RSI, MACD and volume confirm whether the trend has fuel.
    rsi = factors.get("rsi", 50)
    if 50 <= rsi <= 75:
        score += 7
    elif 45 <= rsi < 50 or 75 < rsi <= 82:
        score += 4

    if factors.get("macd_hist", 0) > 0:
        score += 4
    if factors.get("vol_ratio", 1) > 1:
        score += 3
    if factors.get("volume_confirm", 0) > 0:
        score += 2

    return round(min(score, 100), 1)


def _candidate_score(factors: dict[str, float], amount: float, asset_type: str, mode: str = "balanced") -> float:
    score = factors.get("continuation_score", 0.0)
    score += _liquidity_bonus(amount)
    score -= _risk_penalty(factors, asset_type, mode)
    if mode == "strict":
        score -= _strict_missing_confirmation_penalty(factors)
    elif mode == "aggressive":
        score += _aggressive_momentum_bonus(factors)
    return round(max(min(score, 100), 0), 1)


def _liquidity_bonus(amount: float) -> float:
    if amount >= 1_000_000_000:
        return 8
    if amount >= 300_000_000:
        return 6
    if amount >= 100_000_000:
        return 3
    return 0


def _risk_penalty(factors: dict[str, float], asset_type: str, mode: str = "balanced") -> float:
    rsi = factors.get("rsi", 50)
    drawdown = factors.get("drawdown_20", 0)
    ret_5 = factors.get("ret_5", 0)
    ret_20 = factors.get("ret_20", 0)
    volatility = factors.get("volatility", 0)
    consecutive = factors.get("consecutive_up_days", 0)
    penalty = 0.0

    if rsi >= 88:
        penalty += 14
    elif rsi >= 82:
        penalty += 9
    elif rsi >= 78:
        penalty += 4

    if drawdown > -0.5 and ret_5 >= 8:
        penalty += 8
    elif drawdown > -1 and ret_5 >= 5:
        penalty += 4

    if consecutive >= 5 and drawdown > -1:
        penalty += 5

    if asset_type == "ETF":
        if ret_20 >= 30:
            penalty += 6
        elif ret_20 >= 20:
            penalty += 3
        if volatility >= 4:
            penalty += 4
    else:
        if ret_20 >= 50:
            penalty += 8
        elif ret_20 >= 35:
            penalty += 5
        if volatility >= 7:
            penalty += 5

    if mode == "strict":
        penalty *= 1.25
    elif mode == "aggressive":
        penalty *= 0.65
    return penalty


def _strict_missing_confirmation_penalty(factors: dict[str, float]) -> float:
    penalty = 0.0
    if factors.get("volume_confirm", 0) <= 0:
        penalty += 4
    if factors.get("macd_hist", 0) <= 0:
        penalty += 4
    if factors.get("up_days_10", 0) < 5:
        penalty += 3
    return penalty


def _aggressive_momentum_bonus(factors: dict[str, float]) -> float:
    if factors.get("ret_5", 0) > 3 and factors.get("ma20_slope_5", 0) > 1:
        return 4
    return 0


def risk_note(factors: dict[str, float], amount: float, asset_type: str, mode: str = "balanced") -> str:
    notes = []
    rsi = factors.get("rsi", 50)
    drawdown = factors.get("drawdown_20", 0)
    ret_5 = factors.get("ret_5", 0)
    ret_20 = factors.get("ret_20", 0)
    volatility = factors.get("volatility", 0)

    if amount < 100_000_000:
        notes.append("流动性偏低")
    if rsi >= 82:
        notes.append("RSI过热")
    if drawdown > -1 and ret_5 >= 5:
        notes.append("短线接近高位")
    if asset_type == "ETF" and ret_20 >= 20:
        notes.append("20日涨幅偏大")
    if asset_type == "A股" and ret_20 >= 35:
        notes.append("20日涨幅偏大")
    if (asset_type == "ETF" and volatility >= 4) or (asset_type == "A股" and volatility >= 7):
        notes.append("波动偏高")
    if mode == "strict" and factors.get("volume_confirm", 0) <= 0:
        notes.append("量能未确认")
    return "；".join(notes) if notes else "风险可控"


def trade_suggestion(factors: dict[str, float], asset_type: str, mode: str = "balanced") -> str:
    score = factors.get("candidate_score", factors.get("continuation_score", 0))
    trend_structure = factors.get("trend_score", 0)
    drawdown = factors.get("drawdown_20", 0)
    rsi = factors.get("rsi", 50)
    ret_5 = factors.get("ret_5", 0)
    ret_20 = factors.get("ret_20", 0)
    volume_confirm = factors.get("volume_confirm", 0)

    unit = "小仓试探" if asset_type == "A股" else "小额试探"

    if score >= 85:
        if drawdown > -1 and ret_5 >= 5:
            return "等回踩：趋势强但短线贴近高位，不追；回踩1%-3%且不破MA20再看"
        if rsi >= 82:
            return "持有/不追：趋势强但RSI偏热，已有仓位可持有，未持仓等回落"
        return f"{unit}：趋势强，回撤位置尚可；单笔不超过计划资金的10%-15%"

    if score >= 70:
        if -6 <= drawdown <= -1 and trend_structure >= 3:
            return f"{unit}：趋势向上且有回踩，适合加入买入观察；跌破MA20放弃"
        if drawdown > -1:
            return "等回踩：趋势向上但买点偏高，等缩量回踩MA20附近"
        return "观察：趋势尚可，但位置或确认度一般，先等放量转强"

    if score >= 55:
        if volume_confirm > 0 and ret_20 > 0:
            return "观察不买：有转强迹象，等突破后回踩确认"
        return "观望：趋势不够顺，暂不作为优先买入标的"

    if rsi >= 82 or ret_20 >= (35 if asset_type == "A股" else 20):
        return "减仓/回避：短线偏热或涨幅过大，已有仓位考虑分批落袋"

    return "回避：趋势弱，暂不买入"


def sell_suggestion(factors: dict[str, float], asset_type: str) -> str:
    score = factors.get("candidate_score", factors.get("continuation_score", 0))
    drawdown = factors.get("drawdown_20", 0)
    rsi = factors.get("rsi", 50)
    ret_20 = factors.get("ret_20", 0)
    trend_structure = factors.get("trend_score", 0)

    if score >= 70 and drawdown > -8:
        if rsi >= 85 or ret_20 >= (50 if asset_type == "A股" else 30):
            return "已有仓位：可分批止盈10%-30%，保留底仓看趋势"
        return "已有仓位：继续持有，跌破MA20或放量转弱再减"
    if trend_structure < 2 or drawdown <= -10:
        return "已有仓位：趋势走弱，考虑减仓或止损"
    return "已有仓位：轻仓观察，反弹不过前高可减"


def trend_grade(score: float) -> str:
    if score >= 80:
        return "强趋势"
    if score >= 65:
        return "趋势向上"
    if score >= 50:
        return "观察"
    return "偏弱"


def trend_action_note(factors: dict[str, float]) -> str:
    score = factors.get("candidate_score", factors.get("continuation_score", 0))
    drawdown = factors.get("drawdown_20", 0)
    rsi = factors.get("rsi", 50)
    if score >= 80 and drawdown > -1:
        return "强势但接近高位，不追高，等回踩"
    if score >= 65 and -6 <= drawdown <= -1:
        return "趋势较顺，适合加入观察清单"
    if score >= 50:
        return "有转强迹象，等量价继续确认"
    if rsi >= 80:
        return "短线过热，防冲高回落"
    return "趋势不足，暂不优先"


def _score(factors: dict[str, float], current_price: float) -> float:
    if current_price <= 0:
        current_price = 1
    score = 0.0

    # Momentum 30%
    score += min(max(factors.get("ret_5", 0) / 5, -1), 1) * 10
    score += min(max(factors.get("ret_20", 0) / 10, -1), 1) * 10
    score += min(max(factors.get("ret_60", 0) / 20, -1), 1) * 10

    # Trend 25%
    score += factors.get("trend_score", 0) / 4 * 25

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


def _scan_one(
    code: str,
    name: str,
    price: float,
    force_refresh: bool = False,
    asset_type: str = "ETF",
    amount: float = 0.0,
    mode: str = "balanced",
) -> dict[str, Any] | None:
    cache_prefix = STOCK_CACHE_PREFIX if asset_type == "A股" else ETF_CACHE_PREFIX
    cache_key = f"{cache_prefix}_{code}"
    if not force_refresh:
        cached = load_generic_cache(cache_key)
        if cached is not None:
            cached["from_cache"] = True
            return cached

    klines = pd.DataFrame()
    # Try Tencent first — covers all on-exchange funds (ETF + LOF) and has a hard timeout
    try:
        klines = _fetch_tencent_klines(code, days=120)
    except Exception:
        pass

    # Fallback to EastMoney/fetch_history. EastMoney covers both ETFs and A-shares;
    # fetch_history is kept for the ETF-specific fallback path already used elsewhere.
    if klines.empty or len(klines) < 20:
        secid = _etf_secid(code)
        try:
            klines = _fetch_eastmoney_klines(secid, days=120)
        except Exception:
            if asset_type != "ETF":
                return None
            try:
                end = date.today()
                start = end - timedelta(days=80)
                klines, _msgs = fetch_history(secid, start, end)
            except Exception:
                return None

    factors = compute_factors(klines)
    if not factors:
        return None

    score = _score(factors, price)
    candidate_score = _candidate_score(factors, amount, asset_type, mode)
    factors["candidate_score"] = candidate_score
    result = {
        "code": code,
        "name": name,
        "asset_type": asset_type,
        "price": price,
        "amount": amount,
        "score": score,
        "candidate_score": candidate_score,
        "trend_grade": trend_grade(candidate_score),
        "action_note": trend_action_note(factors),
        "risk_note": risk_note(factors, amount, asset_type, mode),
        "trade_suggestion": trade_suggestion(factors, asset_type, mode),
        "sell_suggestion": sell_suggestion(factors, asset_type),
        **factors,
    }
    save_generic_cache(cache_key, result)
    return result


def scan_etfs(top_n: int = DEFAULT_SCAN_LIMIT, max_workers: int = 6, force_refresh: bool = False) -> tuple[pd.DataFrame, list[str]]:
    return scan_market(universe="etf", top_n=top_n, max_workers=max_workers, force_refresh=force_refresh)


def scan_market(
    universe: str = "etf",
    top_n: int = DEFAULT_SCAN_LIMIT,
    max_workers: int = 6,
    force_refresh: bool = False,
    include_defensive: bool = False,
    mode: str = "balanced",
) -> tuple[pd.DataFrame, list[str]]:
    messages: list[str] = []
    start = time.perf_counter()
    universe = universe if universe in MARKET_UNIVERSES else "etf"
    mode = mode if mode in SCAN_MODES else "balanced"
    universe_label = MARKET_UNIVERSES[universe]
    summary_cache_key = f"{SUMMARY_CACHE_PREFIX}_{universe}_{top_n}_{int(include_defensive)}_{mode}"
    if not force_refresh:
        cached_summary = load_generic_cache(summary_cache_key)
        if isinstance(cached_summary, list) and cached_summary:
            return pd.DataFrame(cached_summary), [f"Scanner summary cache hit: {len(cached_summary)} rows."]

    try:
        symbols = fetch_scan_universe(universe, include_defensive=include_defensive)
        messages.append(f"Fetched {len(symbols)} {universe_label} symbols.")
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to fetch {universe_label} list: {exc}"]

    if symbols.empty:
        return pd.DataFrame(), messages

    # Sort by turnover amount, take top N
    symbols = symbols.sort_values("amount", ascending=False).head(top_n).reset_index(drop=True)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _scan_one,
                row["code"],
                row["name"],
                row["price"],
                force_refresh,
                row.get("asset_type", universe_label),
                float(row.get("amount", 0) or 0),
                mode,
            ): row["code"]
            for _, row in symbols.iterrows()
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
    messages.append(f"Scanned {len(results)}/{top_n} {universe_label} symbols in {elapsed:.1f}s.")
    if failed_count > 0:
        messages.append(f"{failed_count} symbol(s) failed — data source timeout or network issue. Try '强制刷新' or check 行情源状态.")

    if not results:
        return pd.DataFrame(), messages

    df = pd.DataFrame(results)
    df = df.sort_values(["candidate_score", "continuation_score", "score"], ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Rename columns for display
    display_cols = {
        "rank": "排名",
        "code": "代码",
        "name": "名称",
        "asset_type": "类型",
        "price": "价格",
        "amount": "成交额",
        "score": "综合评分",
        "candidate_score": "候选分",
        "continuation_score": "连涨趋势分",
        "trend_grade": "趋势等级",
        "trade_suggestion": "买入建议",
        "sell_suggestion": "持有/卖出建议",
        "action_note": "观察建议",
        "risk_note": "风险提示",
        "ret_5": "5日涨幅%",
        "ret_10": "10日涨幅%",
        "ret_20": "20日涨幅%",
        "ret_60": "60日涨幅%",
        "trend_score": "趋势结构分(0-4)",
        "up_days_5": "5日上涨天数",
        "up_days_10": "10日上涨天数",
        "consecutive_up_days": "连续上涨天数",
        "ma20_slope_5": "MA20斜率%",
        "volatility": "波动率%",
        "rsi": "RSI",
        "macd_hist": "MACD柱",
        "drawdown_20": "20日回撤%",
        "vol_ratio": "量比",
        "volume_confirm": "量能确认",
    }
    df = df.rename(columns={k: v for k, v in display_cols.items() if k in df.columns})
    # Only cache when at least half of the requested ETFs succeeded — avoids cache pollution from partial failures
    if len(results) >= top_n / 2:
        save_generic_cache(summary_cache_key, json.loads(df.to_json(orient="records", force_ascii=False)))
    else:
        messages.append(f"Only {len(results)}/{top_n} succeeded, summary not cached — re-scan will retry failed ETFs.")
    return df, messages
