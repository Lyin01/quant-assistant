from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .analytics import add_indicators, latest_signal
from .data_provider import Quote, quote_for_proxy
from .market_data import fetch_history
from .market_scanner import scan_etfs
from .strategy import generate_recommendations, position_strategy_tag, strategy_requires_live_quote


@dataclass
class AgentReport:
    agent: str
    status: str  # ok | warn | error
    findings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    data_report: AgentReport
    analysis_report: AgentReport
    decision_report: AgentReport
    risk_report: AgentReport
    final_summary: str = ""


def run_pipeline(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote] | None = None,
    scan_top_n: int = 10,
) -> PipelineResult:
    """Run the multi-agent analysis pipeline.

    Agents:
    1. Data Agent — verify quotes, fetch missing history, scan market.
    2. Analysis Agent — technical signals (MA, RSI, MACD) for each proxy.
    3. Decision Agent — run strategy engine, summarize actionable items.
    4. Risk Agent — cash stress, concentration, uncovered positions, drawdown.
    """
    quotes = quotes or {}

    data_report = _data_agent(config, portfolio, quotes, scan_top_n)
    analysis_report = _analysis_agent(config, portfolio, quotes)
    decision_report = _decision_agent(config, portfolio, quotes)
    risk_report = _risk_agent(config, portfolio, quotes)

    # Build final summary from all agents
    parts = []
    if decision_report.findings:
        parts.append("【决策】" + "；".join(decision_report.findings[:3]))
    if risk_report.findings:
        parts.append("【风控】" + "；".join(risk_report.findings[:3]))
    if analysis_report.findings:
        parts.append("【分析】" + "；".join(analysis_report.findings[:2]))
    if data_report.findings:
        parts.append("【数据】" + "；".join(data_report.findings[:2]))

    final_summary = "\n".join(parts) if parts else "暂无明确信号，继续观察。"

    return PipelineResult(
        data_report=data_report,
        analysis_report=analysis_report,
        decision_report=decision_report,
        risk_report=risk_report,
        final_summary=final_summary,
    )


def _data_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
    scan_top_n: int,
) -> AgentReport:
    findings: list[str] = []
    data: dict[str, Any] = {}

    # Quote coverage
    proxies = _mapping(_mapping(config).get("quotes")).get("proxies", {})
    proxies = _mapping(proxies)
    needed = set()
    accounts = _mapping(portfolio).get("accounts", {})
    if not isinstance(accounts, dict):
        accounts = {}
    for account_key, account in accounts.items():
        for p in _positions(account):
            tag = _safe_position_strategy_tag(config, p, account_key)
            if not strategy_requires_live_quote(tag, account_key):
                continue
            proxy = p.get("market_proxy")
            if proxy and proxy in proxies:
                needed.add(proxy)

    covered = {proxy for proxy in needed if quote_for_proxy(proxy, config, quotes)}
    missing = needed - covered

    if missing:
        findings.append(f"行情缺失: {', '.join(sorted(missing))}")
    else:
        findings.append(f"行情覆盖: {len(covered)}/{len(needed)} 个代理")

    # Market scan (lightweight, cached)
    try:
        scan_df, scan_msgs = scan_etfs(top_n=scan_top_n)
        if not scan_df.empty:
            top3 = scan_df.head(3)["名称"].tolist() if "名称" in scan_df.columns else []
            findings.append(f"ETF扫描Top3: {', '.join(top3)}")
            data["scan_top3"] = top3
        data["scan_messages"] = scan_msgs
    except Exception as exc:
        findings.append(f"ETF扫描失败: {exc}")

    status = "warn" if missing else "ok"
    return AgentReport(agent="数据Agent", status=status, findings=findings, data=data)


def _analysis_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> AgentReport:
    findings: list[str] = []
    data: dict[str, Any] = {}

    proxies = _mapping(_mapping(config).get("quotes")).get("proxies", {})
    proxies = _mapping(proxies)
    from datetime import date, timedelta

    accounts = _mapping(portfolio).get("accounts", {})
    if not isinstance(accounts, dict):
        accounts = {}
    for account in accounts.values():
        for p in _positions(account):
            proxy = p.get("market_proxy")
            if not proxy or proxy not in proxies:
                continue
            secid = proxies[proxy]
            try:
                end = date.today()
                start = end - timedelta(days=120)
                klines, _ = fetch_history(secid, start, end)
                if klines.empty or len(klines) < 20:
                    continue
                sig = latest_signal(klines)
                name = str(p.get("name", ""))
                data[f"{name}_signal"] = sig
                if sig.get("signal") in ("趋势向上", "低吸观察"):
                    findings.append(f"{name}: {sig['signal']} ({sig.get('reason', '')})")
                elif sig.get("signal") in ("防守观望",):
                    findings.append(f"{name}: {sig['signal']} — 注意风险")
            except Exception:
                continue

    status = "ok" if findings else "warn"
    return AgentReport(agent="分析Agent", status=status, findings=findings, data=data)


def _decision_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> AgentReport:
    recs = _recommendations(generate_recommendations(config, portfolio, quotes))
    actionable = [
        r
        for r in recs
        if r.get("action") in {"BUY", "SELL", "LIMIT_BUY"}
        and all(key in r for key in ("instrument", "amount", "reason"))
    ]
    holds = [r for r in recs if r.get("action") == "HOLD"]

    findings: list[str] = []
    if actionable:
        for r in actionable:
            findings.append(f"{r['action']} {r['instrument']} {r['amount']} — {r['reason']}")
    else:
        findings.append("无触发操作，全部HOLD")

    # Cash-aware decision modifier
    stock = _account(portfolio, "stock")
    cash = _number(stock.get("available_cash"))
    if cash < 100 and any(r["action"] == "BUY" for r in actionable):
        findings.append(f"⚠️ 可用现金仅 {cash:.2f} 元，买入建议无法执行")

    data = {"actionable_count": len(actionable), "hold_count": len(holds), "recommendations": recs}
    status = "ok" if actionable else "warn"
    return AgentReport(agent="决策Agent", status=status, findings=findings, data=data)


def _recommendations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _account(portfolio: dict[str, Any], account_key: str) -> dict[str, Any]:
    accounts = _mapping(portfolio).get("accounts", {})
    if not isinstance(accounts, dict):
        return {}
    account = accounts.get(account_key, {})
    return account if isinstance(account, dict) else {}


def _positions(account: Any) -> list[dict[str, Any]]:
    if not isinstance(account, dict):
        return []
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        return []
    return [position for position in positions if isinstance(position, dict)]


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_position_strategy_tag(config: dict[str, Any], position: dict[str, Any], account_key: str) -> str:
    try:
        return position_strategy_tag(config, position, account_key)
    except (TypeError, ValueError):
        return str(position.get("tag", "unknown") or "unknown")


def _risk_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> AgentReport:
    findings: list[str] = []
    data: dict[str, Any] = {}

    fund = _account(portfolio, "fund")
    stock = _account(portfolio, "stock")

    # Cash stress
    cash = _number(stock.get("available_cash"))
    if cash < 100:
        findings.append(f"现金紧张: 股票可用仅 {cash:.2f} 元")
        data["cash_stress"] = True
    else:
        data["cash_stress"] = False

    # Concentration
    stock_positions = _positions(stock)
    mv_total = _number(stock.get("market_value"))
    if stock_positions and mv_total > 0:
        top = max(stock_positions, key=lambda p: _number(p.get("market_value")))
        top_market_value = _number(top.get("market_value"))
        pct = top_market_value / mv_total * 100
        data["top_concentration_pct"] = round(pct, 2)
        data["top_name"] = str(top.get("name", ""))
        if pct > 50:
            findings.append(f"高度集中: {top.get('name', '')} 占股票市值 {pct:.1f}%")
        elif pct > 30:
            findings.append(f"仓位集中: {top.get('name', '')} 占股票市值 {pct:.1f}%")

    # Uncovered positions
    uncovered = [p for p in stock_positions if _safe_position_strategy_tag(config, p, "stock") == "imported"]
    if uncovered:
        names = [str(p.get("name", "")) for p in uncovered]
        findings.append(f"无策略覆盖: {', '.join(names)}")
        data["uncovered"] = names

    # Drawdown check for fund positions
    for p in _positions(fund):
        pnl_pct = _number(p.get("holding_pnl_pct"))
        if pnl_pct <= -10:
            findings.append(f"深套: {p.get('name', '')} 持有收益 {pnl_pct:.2f}%")

    status = "warn" if findings else "ok"
    return AgentReport(agent="风控Agent", status=status, findings=findings, data=data)
