from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache


# Predefined commodity chains with representative futures/spot symbols
CHAINS: dict[str, dict[str, Any]] = {
    "锂电池": {
        "description": "上游锂矿 → 中游正极/电解液 → 下游电池/电动车",
        "links": [
            {"name": "碳酸锂", "source": "futures", "code": "LC", "unit": "元/吨"},
            {"name": "氢氧化锂", "source": "spot", "code": "氢氧化锂", "unit": "元/吨"},
            {"name": "钴", "source": "spot", "code": "钴", "unit": "元/吨"},
            {"name": "镍", "source": "futures", "code": "NI", "unit": "元/吨"},
        ],
    },
    "光伏": {
        "description": "上游硅料 → 中游硅片/电池片 → 下游组件/电站",
        "links": [
            {"name": "多晶硅", "source": "spot", "code": "多晶硅", "unit": "元/千克"},
            {"name": "硅片", "source": "spot", "code": "硅片", "unit": "元/片"},
            {"name": "光伏组件", "source": "spot", "code": "光伏组件", "unit": "元/瓦"},
        ],
    },
    "半导体": {
        "description": "上游设备/材料 → 中游制造 → 下游设计/应用",
        "links": [
            {"name": "电子级硅", "source": "spot", "code": "电子级硅", "unit": "美元/千克"},
            {"name": "光刻胶", "source": "spot", "code": "光刻胶", "unit": "元/克"},
        ],
    },
    "铜产业链": {
        "description": "上游铜矿 → 中游冶炼 → 下游电力/电子/建筑",
        "links": [
            {"name": "铜期货", "source": "futures", "code": "CU", "unit": "元/吨"},
            {"name": "铜现货", "source": "spot", "code": "铜", "unit": "元/吨"},
        ],
    },
}


# Sina futures continuous contract mapping
SINA_FUTURES_MAP: dict[str, str | None] = {
    "CU": "CU0",   # 沪铜连续
    "LC": "LC0",   # 碳酸锂连续 (广州期货交易所)
    "CO": None,    # 钴没有期货合约
    "NI": "NI0",   # 沪镍连续
}


def _fetch_sina_futures(symbol: str) -> tuple[float | None, str]:
    """Fetch futures price from Sina real-time API."""
    sina_code = SINA_FUTURES_MAP.get(symbol)
    if sina_code is None:
        return None, f"Sina futures: {symbol} has no continuous contract"

    try:
        url = f"https://hq.sinajs.cn/list={sina_code}"
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://finance.sina.com.cn/futures/",
                "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode("gbk", errors="replace")

        # Parse: var hq_str_CU0="沪铜连续,74490.00,74440.00,...";
        if '="' not in text:
            return None, "Sina futures: unexpected response format"

        data_part = text.split('="')[1].rstrip('";')
        parts = data_part.split(",")
        if len(parts) < 2:
            return None, "Sina futures: no price data"

        price = float(parts[1])
        return price, "Sina futures: ok"
    except Exception as exc:
        return None, f"Sina futures: {exc}"


def _fetch_eastmoney_futures_quote(symbol: str) -> tuple[float | None, str]:
    """Fetch futures price from EastMoney real-time quote API."""
    mapping = {"CU": "cu", "LC": "lc", "CO": "co", "NI": "ni"}
    em_code = mapping.get(symbol, symbol.lower())

    # Try markets: Shanghai(113), Dalian(114), Zhengzhou(115), Guangzhou(142)
    markets = [("113", "SHFE"), ("114", "DCE"), ("115", "CZCE"), ("142", "GFEX")]
    for market, name in markets:
        try:
            params = {
                "secid": f"{market}.{em_code}0",
                "fields": "f43,f57,f58",
            }
            url = "https://push2.eastmoney.com/api/qt/stock/get?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://quote.eastmoney.com/",
                    "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))

            data = payload.get("data") or {}
            if data.get("f57"):
                price_raw = data.get("f43")
                if price_raw is not None:
                    price_raw = float(price_raw)
                    # f43 scaling: infer from magnitude
                    if price_raw > 1_000_000:
                        price = price_raw / 10_000
                    elif price_raw > 100_000:
                        price = price_raw / 1_000
                    elif price_raw > 10_000:
                        price = price_raw / 100
                    elif price_raw > 1_000:
                        price = price_raw / 10
                    else:
                        price = price_raw
                    return price, f"EastMoney futures ({name}): ok"
        except Exception:
            continue

    return None, f"EastMoney futures: {symbol} not found"


def _fetch_futures_price(symbol: str) -> tuple[float | None, str]:
    """Try multiple sources for futures price."""
    # Try Sina first (most reliable for continuous contracts)
    price, msg = _fetch_sina_futures(symbol)
    if price is not None:
        return price, msg

    # Fallback to EastMoney real-time quote
    return _fetch_eastmoney_futures_quote(symbol)


def _fetch_akshare_spot(name: str) -> tuple[float | None, str]:
    """Try various akshare functions for spot/commodity prices."""
    try:
        import akshare as ak
    except Exception as exc:
        return None, f"AkShare import failed: {exc}"

    # List of candidate functions that may provide commodity/spot data
    candidates = [
        "spot_price_qhdp",
        "spot_price_lme",
        "futures_zh_spot",
        "futures_display_main_sina",
        "futures_zh_realtime",
        "spot_hist_sge",
        "futures_main_sina",
    ]

    for fn_name in candidates:
        try:
            fn = getattr(ak, fn_name)
            df = fn()
            if df is None or df.empty:
                continue

            # Try to find a column containing the commodity name
            for col in df.columns:
                try:
                    matches = df[col].astype(str).str.contains(name, na=False)
                except Exception:
                    continue
                if matches.any():
                    match = df[matches]
                    if not match.empty:
                        # Look for a price column
                        for price_col in ["最新价", "close", "price", "最新价格", "收盘价", "价格", "现价", "latest", "f2"]:
                            if price_col in match.columns:
                                val = match.iloc[0][price_col]
                                if val is not None and str(val) not in ("", "nan", "None"):
                                    return float(str(val).replace(",", "")), f"{fn_name}: ok"
                        # Fallback: second-to-last column (often price)
                        try:
                            val = match.iloc[0].iloc[-2]
                            if val is not None and str(val) not in ("", "nan", "None"):
                                return float(str(val).replace(",", "")), f"{fn_name}: ok"
                        except Exception:
                            pass
        except Exception:
            continue

    return None, f"spot price for {name}: not found in any source"


def fetch_chain_prices(chain_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    cache_key = f"chain_{chain_name}"
    cached = load_generic_cache(cache_key)
    if cached is not None:
        return cached, ["Chain: cache hit"]

    chain = CHAINS.get(chain_name)
    if not chain:
        return [], [f"Unknown chain: {chain_name}"]

    results: list[dict[str, Any]] = []
    messages: list[str] = []

    for link in chain["links"]:
        name = link["name"]
        source = link["source"]
        code = link["code"]
        unit = link["unit"]

        if source == "futures":
            price, msg = _fetch_futures_price(code)
        else:
            price, msg = _fetch_akshare_spot(code)

        messages.append(msg)
        if price is not None:
            results.append({
                "环节": name,
                "价格": price,
                "单位": unit,
                "来源": source,
            })

    if results:
        save_generic_cache(cache_key, results)
    else:
        messages.append("No valid prices fetched — all sources failed.")

    return results, messages


def list_chains() -> list[str]:
    return list(CHAINS.keys())


def chain_summary(chain_name: str) -> dict[str, Any] | None:
    chain = CHAINS.get(chain_name)
    if not chain:
        return None
    return {
        "name": chain_name,
        "description": chain["description"],
        "links": [link["name"] for link in chain["links"]],
    }
