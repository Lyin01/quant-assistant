from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from .data_source_health import record_request


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
        quotes, _messages = self.get_quotes_with_status(secids)
        return quotes

    def get_quotes_with_status(self, secids: list[str]) -> tuple[dict[str, Quote], list[str]]:
        if not secids:
            return {}, ["EastMoney: no secids requested."]

        params = {
            "fltt": "2",
            "secids": ",".join(sorted(set(secids))),
            "fields": "f12,f14,f2,f3,f4,f124",
        }
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://quote.eastmoney.com/",
                "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return {}, [f"EastMoney: request failed: {exc}"]

        rows = payload.get("data", {}).get("diff") or []
        if not rows:
            return {}, ["EastMoney: response contained no quote rows."]

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
        return quotes, [f"EastMoney: loaded {len(quotes)} quotes."]


class AkShareProvider:
    def get_quotes(self, secids: list[str]) -> dict[str, Quote]:
        quotes, _messages = self.get_quotes_with_status(secids)
        return quotes

    def get_quotes_with_status(self, secids: list[str]) -> tuple[dict[str, Quote], list[str]]:
        if not secids:
            return {}, ["AkShare: no secids requested."]

        try:
            import akshare as ak
        except Exception as exc:
            return {}, [f"AkShare: import failed: {exc}"]

        codes = {_code_from_secid(secid): secid for secid in secids}
        quotes: dict[str, Quote] = {}
        messages: list[str] = []

        fetchers = [
            ("AkShare index", ak.stock_zh_index_spot_em),
            ("AkShare ETF", ak.fund_etf_spot_em),
        ]

        for label, fetcher in fetchers:
            try:
                frame = fetcher()
            except Exception as exc:
                messages.append(f"{label}: request failed: {exc}")
                continue

            loaded = _quotes_from_frame(frame, codes)
            quotes.update(loaded)
            messages.append(f"{label}: loaded {len(loaded)} matching quotes.")

        if not quotes:
            messages.append("AkShare: no matching quote rows.")
        return quotes, messages


class TencentProvider:
    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

    def get_quotes(self, secids: list[str]) -> dict[str, Quote]:
        quotes, _messages = self.get_quotes_with_status(secids)
        return quotes

    def get_quotes_with_status(self, secids: list[str]) -> tuple[dict[str, Quote], list[str]]:
        if not secids:
            return {}, ["Tencent: no secids requested."]

        symbols = {_tencent_symbol(secid): secid for secid in sorted(set(secids))}
        params = {"q": ",".join(f"s_{symbol}" for symbol in symbols)}
        url = "https://qt.gtimg.cn/q=" + params["q"]
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://gu.qq.com/",
                "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("gbk", errors="ignore")
        except Exception as exc:
            return {}, [f"Tencent: request failed: {exc}"]

        now = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        quotes: dict[str, Quote] = {}
        for line in text.splitlines():
            if '="' not in line:
                continue
            symbol = line.split('="', 1)[0].replace("v_s_", "")
            secid = symbols.get(symbol)
            if not secid:
                continue
            payload = line.split('="', 1)[1].rstrip('";')
            fields = payload.split("~")
            if len(fields) < 6:
                continue
            quotes[secid] = Quote(
                secid=secid,
                code=fields[2],
                name=fields[1],
                price=_num(fields[3]),
                pct=_num(fields[5]),
                change=_num(fields[4]),
                time_text=now,
            )

        if not quotes:
            return {}, ["Tencent: response contained no matching quote rows."]
        return quotes, [f"Tencent: loaded {len(quotes)} quotes."]


class AutoProvider:
    def __init__(self, timeout: int = 8) -> None:
        self.akshare = AkShareProvider()
        self.eastmoney = EastMoneyProvider(timeout=timeout)
        self.tencent = TencentProvider(timeout=timeout)

    def get_quotes(self, secids: list[str]) -> dict[str, Quote]:
        quotes, _messages = self.get_quotes_with_status(secids)
        return quotes

    def get_quotes_with_status(self, secids: list[str]) -> tuple[dict[str, Quote], list[str]]:
        """Fetch quotes in parallel from all providers, return as soon as we have enough."""
        if not secids:
            return {}, ["AutoProvider: no secids requested."]

        # Eager-import akshare so the worker thread doesn't pay first-import cost.
        try:
            import akshare as ak  # noqa: F401
        except Exception:
            pass

        def _fetch(fn, name, targets):
            start = time.perf_counter()
            try:
                q, m = fn(targets)
            except Exception as exc:
                q, m = {}, [f"{name}: failed: {exc}"]
            latency_ms = (time.perf_counter() - start) * 1000
            success = len(q)
            record_request(name, requested=len(targets), success=success, failed=len(targets) - success, latency_ms=latency_ms)
            return q, m, name

        quotes: dict[str, Quote] = {}
        messages: list[str] = []

        # Phase 1: Race all three providers; use whoever returns first.
        executor = ThreadPoolExecutor(max_workers=3)
        futures = {
            executor.submit(_fetch, self.eastmoney.get_quotes_with_status, "eastmoney", secids): "eastmoney",
            executor.submit(_fetch, self.akshare.get_quotes_with_status, "akshare", secids): "akshare",
            executor.submit(_fetch, self.tencent.get_quotes_with_status, "tencent", secids): "tencent",
        }

        done, not_done = wait(list(futures.keys()), timeout=2, return_when=FIRST_COMPLETED)

        for future in done:
            q, m, name = future.result()
            quotes.update(q)
            messages.extend(m)

        # Phase 2: If still missing, wait up to 2 more seconds for remaining providers.
        missing = sorted(set(secids) - set(quotes))
        if missing and not_done:
            done2, _ = wait(list(not_done), timeout=2)
            for future in done2:
                q, m, name = future.result()
                quotes.update(q)
                messages.extend(m)

        # Critical: do NOT block on slow/blocked outbound requests.
        executor.shutdown(wait=False)

        missing = sorted(set(secids) - set(quotes))
        if missing:
            messages.append(f"AutoProvider: {len(missing)} quotes still missing after all attempts.")

        return quotes, messages


def build_provider(config: dict[str, Any]) -> AutoProvider | AkShareProvider | EastMoneyProvider | TencentProvider:
    provider_config = config.get("market_provider", {})
    name = str(provider_config.get("name", "auto")).lower()
    timeout = int(provider_config.get("timeout_seconds", 8))

    if name == "akshare":
        return AkShareProvider()
    if name == "eastmoney":
        return EastMoneyProvider(timeout=timeout)
    if name == "tencent":
        return TencentProvider(timeout=timeout)
    return AutoProvider(timeout=timeout)


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


def quote_status(config: dict[str, Any]) -> str:
    provider_name = config.get("market_provider", {}).get("name", "auto")
    decision_mode = config.get("market_provider", {}).get("use_live_proxy_for_decisions", False)
    mode = "实时行情参与策略判断" if decision_mode else "实时行情仅展示，策略按持仓快照判断"
    return f"行情源: {provider_name}; {mode}."


def _num(value: object) -> float | None:
    if value in (None, "-", ""):
        return None
    try:
        cleaned = str(value).replace("%", "").replace(",", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _infer_secid(code: object, requested_secids: str) -> str:
    code_text = str(code)
    for secid in requested_secids.split(","):
        if secid.endswith("." + code_text):
            return secid
    return code_text


def _code_from_secid(secid: str) -> str:
    if "." in secid:
        return _normalize_code(secid.split(".", 1)[1])
    return _normalize_code(secid)


def _quotes_from_frame(frame: Any, codes: dict[str, str]) -> dict[str, Quote]:
    if frame is None or getattr(frame, "empty", True):
        return {}

    code_column = _first_existing_column(frame, ["代码", "code", "symbol"])
    name_column = _first_existing_column(frame, ["名称", "name"])
    price_column = _first_existing_column(frame, ["最新价", "最新", "price"])
    pct_column = _first_existing_column(frame, ["涨跌幅", "涨跌幅%", "changepercent"])
    change_column = _first_existing_column(frame, ["涨跌额", "涨跌", "change"])

    if not code_column:
        return {}

    now = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    quotes: dict[str, Quote] = {}
    for _index, row in frame.iterrows():
        code = _normalize_code(row.get(code_column, ""))
        secid = codes.get(code)
        if not secid:
            continue

        quotes[secid] = Quote(
            secid=secid,
            code=code,
            name=str(row.get(name_column, "")) if name_column else code,
            price=_num(row.get(price_column)) if price_column else None,
            pct=_num(row.get(pct_column)) if pct_column else None,
            change=_num(row.get(change_column)) if change_column else None,
            time_text=now,
        )
    return quotes


def _first_existing_column(frame: Any, names: list[str]) -> str | None:
    columns = set(str(column) for column in getattr(frame, "columns", []))
    for name in names:
        if name in columns:
            return name
    return None


def _normalize_code(value: object) -> str:
    text = str(value).strip()
    digits = "".join(character for character in text if character.isdigit())
    if digits:
        return digits[-6:].zfill(6)
    return text.zfill(6)


def _tencent_symbol(secid: str) -> str:
    market, _dot, code = secid.partition(".")
    prefix = "sz" if market == "0" else "sh"
    return f"{prefix}{_normalize_code(code or secid)}"
