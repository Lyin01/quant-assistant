from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_cached, save_cached


# Predefined commodity chains with representative futures/spot symbols
CHAINS: dict[str, dict[str, Any]] = {
    "锂电池": {
        "description": "上游锂矿 → 中游正极/电解液 → 下游电池/电动车",
        "links": [
            {"name": "碳酸锂", "source": "futures", "code": "LC", "unit": "元/吨"},
            {"name": "氢氧化锂", "source": "spot", "code": "氢氧化锂", "unit": "元/吨"},
            {"name": "钴", "source": "futures", "code": "CO", "unit": "元/吨"},
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


def _fetch_akshare_spot(name: str) -> tuple[float | None, str]:
    try:
        import akshare as ak
        # Try multiple spot price sources
        for fn_name in ["spot_price_qhdp", "spot_price_lme"]:
            try:
                fn = getattr(ak, fn_name)
                df = fn()
                if df is not None and not df.empty:
                    match = df[df.iloc[:, 0].astype(str).str.contains(name, na=False)]
                    if not match.empty:
                        val = match.iloc[0].get("最新价") or match.iloc[0].iloc[-2]
                        return float(str(val).replace(",", "")), f"{fn_name}: ok"
            except Exception:
                continue
        return None, f"spot price for {name}: not found"
    except Exception as exc:
        return None, f"spot price for {name}: {exc}"


def _fetch_eastmoney_futures(symbol: str) -> tuple[float | None, str]:
    try:
        # Map symbol to EastMoney futures code
        mapping = {"CU": "cu", "LC": "lc", "CO": "co", "NI": "ni"}
        em_code = mapping.get(symbol, symbol.lower())
        params = {
            "lmt": "1",
            "secid": f"113.{em_code}0",
            "fields1": "f1",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        }
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = (payload.get("data") or {}).get("klines") or []
        if rows:
            fields = str(rows[-1]).split(",")
            if len(fields) >= 2:
                return float(fields[2]), "EastMoney futures: ok"
        return None, "EastMoney futures: no data"
    except Exception as exc:
        return None, f"EastMoney futures: {exc}"


def fetch_chain_prices(chain_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    cache_key = f"chain_{chain_name}"
    cached = load_cached(cache_key)
    if cached is not None:
        return cached, ["Chain: cache hit"]

    chain = CHAINS.get(chain_name)
    if not chain:
        return [], [f"Unknown chain: {chain_name}"]

    results = []
    messages = []

    for link in chain["links"]:
        name = link["name"]
        source = link["source"]
        code = link["code"]
        unit = link["unit"]

        if source == "futures":
            price, msg = _fetch_eastmoney_futures(code)
        else:
            price, msg = _fetch_akshare_spot(code)

        messages.append(msg)
        results.append({
            "环节": name,
            "价格": price,
            "单位": unit,
            "来源": source,
        })

    save_cached(cache_key, results)
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
