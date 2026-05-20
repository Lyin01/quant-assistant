from __future__ import annotations

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
    proxies = config.get("quotes", {}).get("proxies", {})
    needed = set()
    for account_key, account in portfolio.get("accounts", {}).items():
        for p in account.get("positions", []):
            tag = position_strategy_tag(config, p, account_key)
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

    proxies = config.get("quotes", {}).get("proxies", {})
    from datetime import date, timedelta

    for account in portfolio.get("accounts", {}).values():
        for p in account.get("positions", []):
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
                data[f"{p['name']}_signal"] = sig
                if sig.get("signal") in ("趋势向上", "低吸观察"):
                    findings.append(f"{p['name']}: {sig['signal']} ({sig.get('reason', '')})")
                elif sig.get("signal") in ("防守观望",):
                    findings.append(f"{p['name']}: {sig['signal']} — 注意风险")
            except Exception:
                continue

    status = "ok" if findings else "warn"
    return AgentReport(agent="分析Agent", status=status, findings=findings, data=data)


def _decision_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> AgentReport:
    recs = generate_recommendations(config, portfolio, quotes)
    actionable = [r for r in recs if r["action"] in {"BUY", "SELL", "LIMIT_BUY"}]
    holds = [r for r in recs if r["action"] == "HOLD"]

    findings: list[str] = []
    if actionable:
        for r in actionable:
            findings.append(f"{r['action']} {r['instrument']} {r['amount']} — {r['reason']}")
    else:
        findings.append("无触发操作，全部HOLD")

    # Cash-aware decision modifier
    stock = portfolio["accounts"]["stock"]
    cash = stock.get("available_cash", 0)
    if cash < 100 and any(r["action"] == "BUY" for r in actionable):
        findings.append(f"⚠️ 可用现金仅 {cash:.2f} 元，买入建议无法执行")

    data = {"actionable_count": len(actionable), "hold_count": len(holds), "recommendations": recs}
    status = "ok" if actionable else "warn"
    return AgentReport(agent="决策Agent", status=status, findings=findings, data=data)


def _risk_agent(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> AgentReport:
    findings: list[str] = []
    data: dict[str, Any] = {}

    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]
    total = fund.get("total_assets", 0) + stock.get("total_assets", 0)

    # Cash stress
    cash = stock.get("available_cash", 0)
    if cash < 100:
        findings.append(f"现金紧张: 股票可用仅 {cash:.2f} 元")
        data["cash_stress"] = True
    else:
        data["cash_stress"] = False

    # Concentration
    stock_positions = stock.get("positions", [])
    mv_total = stock.get("market_value", 0)
    if stock_positions and mv_total > 0:
        top = max(stock_positions, key=lambda p: p.get("market_value", 0))
        pct = top["market_value"] / mv_total * 100
        data["top_concentration_pct"] = round(pct, 2)
        data["top_name"] = top["name"]
        if pct > 50:
            findings.append(f"高度集中: {top['name']} 占股票市值 {pct:.1f}%")
        elif pct > 30:
            findings.append(f"仓位集中: {top['name']} 占股票市值 {pct:.1f}%")

    # Uncovered positions
    uncovered = [p for p in stock_positions if position_strategy_tag(config, p, "stock") == "imported"]
    if uncovered:
        names = [p["name"] for p in uncovered]
        findings.append(f"无策略覆盖: {', '.join(names)}")
        data["uncovered"] = names

    # Drawdown check for fund positions
    for p in fund.get("positions", []):
        pnl_pct = p.get("holding_pnl_pct", 0)
        if pnl_pct <= -10:
            findings.append(f"深套: {p['name']} 持有收益 {pnl_pct:.2f}%")

    status = "warn" if findings else "ok"
    return AgentReport(agent="风控Agent", status=status, findings=findings, data=data)
