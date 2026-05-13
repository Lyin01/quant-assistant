from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


CHINA_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Quote:
    secid: str
    code: str
    name: str
    price: float | None
    pct: float | None
    change: float | None
    time_text: str


class EastMoneyProvider:
    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

    def get_quotes(self, secids: list[str]) -> dict[str, Quote]:
        if not secids:
            return {}

        params = {
            "fltt": "2",
            "secids": ",".join(sorted(set(secids))),
            "fields": "f12,f14,f2,f3,f4,f124",
        }
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"Referer": "https://quote.eastmoney.com/"})

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}

        rows = payload.get("data", {}).get("diff") or []
        quotes: dict[str, Quote] = {}
        for row in rows:
            secid = _infer_secid(row.get("f12"), params["secids"])
            timestamp = row.get("f124")
            time_text = ""
            if isinstance(timestamp, int) and timestamp > 0:
                time_text = datetime.fromtimestamp(timestamp, CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")

            quote = Quote(
                secid=secid,
                code=str(row.get("f12", "")),
                name=str(row.get("f14", "")),
                price=_num(row.get("f2")),
                pct=_num(row.get("f3")),
                change=_num(row.get("f4")),
                time_text=time_text,
            )
            quotes[secid] = quote
        return quotes


def collect_secids(config: dict[str, Any], portfolio: dict[str, Any]) -> list[str]:
    proxies = config.get("quotes", {}).get("proxies", {})
    market = config.get("quotes", {}).get("market", {})
    secids = list(market.values()) + list(proxies.values())

    for account in portfolio.get("accounts", {}).values():
        for position in account.get("positions", []):
            proxy_name = position.get("market_proxy")
            secid = proxies.get(proxy_name)
            if secid:
                secids.append(secid)
    return sorted(set(secids))


def quote_for_proxy(
    proxy_name: str | None,
    config: dict[str, Any],
    quotes: dict[str, Quote],
) -> Quote | None:
    if not proxy_name:
        return None
    secid = config.get("quotes", {}).get("proxies", {}).get(proxy_name)
    if not secid:
        return None
    return quotes.get(secid)


def _num(value: object) -> float | None:
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_secid(code: object, requested_secids: str) -> str:
    code_text = str(code)
    for secid in requested_secids.split(","):
        if secid.endswith("." + code_text):
            return secid
    return code_text
