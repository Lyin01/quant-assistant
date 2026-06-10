from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .multi_agent import run_pipeline


def generate_daily_report(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Any] | None = None,
    scan_top_n: int = 10,
) -> dict[str, Any]:
    """Generate a structured daily report.

    Returns a dict with sections for review, signals, actions, risks,
    and tomorrow's plan.
    """
    quotes = quotes or {}
    as_of = portfolio.get("as_of", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Run multi-agent pipeline
    pipe = run_pipeline(config, portfolio, quotes=quotes, scan_top_n=scan_top_n)

    # Extract key numbers
    fund = _account(portfolio, "fund")
    stock = _account(portfolio, "stock")
    fund_assets = _number(fund.get("total_assets"))
    stock_assets = _number(stock.get("total_assets"))
    fund_pnl = _number(fund.get("today_pnl"))
    stock_pnl = _number(stock.get("today_pnl"))
    stock_cash = _number(stock.get("available_cash"))
    total_assets = fund_assets + stock_assets
    total_pnl = fund_pnl + stock_pnl

    # Actionable items
    recs = _recommendations(pipe)
    actionable = [r for r in recs if r.get("action") in {"BUY", "SELL", "LIMIT_BUY"}]

    # Build report sections
    report = {
        "meta": {
            "date": str(date.today()),
            "as_of": as_of,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": {
            "total_assets": round(total_assets, 2),
            "today_pnl": round(total_pnl, 2),
            "fund_assets": round(fund_assets, 2),
            "stock_assets": round(stock_assets, 2),
            "stock_cash": round(stock_cash, 2),
            "actionable_count": len(actionable),
        },
        "今日复盘": {
            "账户表现": f"总资产 {total_assets:.2f}，今日盈亏 {total_pnl:.2f}",
            "规则触发": [
                f"{r.get('action', '')} {r.get('instrument', '')} {r.get('amount', '')} — {r.get('reason', '')}"
                for r in actionable
            ],
            "Agent综合摘要": pipe.final_summary,
        },
        "持仓信号": {
            "技术分析": pipe.analysis_report.findings,
            "数据状态": pipe.data_report.findings,
        },
        "风险提示": pipe.risk_report.findings,
        "明日计划": _tomorrow_plan(pipe, stock_cash),
    }

    return report


def _account(portfolio: dict[str, Any], account_key: str) -> dict[str, Any]:
    accounts = portfolio.get("accounts")
    if not isinstance(accounts, dict):
        return {}
    account = accounts.get(account_key, {})
    return account if isinstance(account, dict) else {}


def _recommendations(pipe: Any) -> list[dict[str, Any]]:
    data = getattr(getattr(pipe, "decision_report", None), "data", {})
    if not isinstance(data, dict):
        return []
    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        return []
    return [item for item in recommendations if isinstance(item, dict)]


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _tomorrow_plan(pipe, cash: float) -> list[str]:
    """Generate tomorrow's watchlist based on pipeline results."""
    plans: list[str] = []

    # From decision agent
    for r in _recommendations(pipe):
        action = str(r.get("action", ""))
        if action == "HOLD":
            continue
        instrument = str(r.get("instrument", "")).strip()
        amount = str(r.get("amount", "")).strip()
        if not instrument and not action:
            continue
        plans.append(f"关注 {instrument}: {action} {amount}".strip())

    # From risk agent
    if cash < 100:
        plans.append("现金紧张，明日如有买入计划需先银证转账补充子弹")

    for finding in pipe.risk_report.findings:
        if "无策略覆盖" in finding:
            plans.append(f"补充策略规则: {finding}")
        elif "集中" in finding:
            plans.append("考虑分散持仓，降低单票集中度")

    # From analysis agent
    for finding in pipe.analysis_report.findings:
        if "低吸观察" in finding:
            name = finding.split(":")[0]
            plans.append(f"{name} 进入低吸观察区，明日关注是否企稳")
        elif "防守观望" in finding:
            name = finding.split(":")[0]
            plans.append(f"{name} 跌破均线，明日不急于抄底")

    if not plans:
        plans.append("暂无明确计划，继续观察")

    return plans


def render_report_markdown(report: dict[str, Any]) -> str:
    """Render the daily report as Markdown for display or messaging."""
    lines = []
    meta = report["meta"]
    lines.append(f"# 每日复盘报告 ({meta['date']})")
    lines.append(f"> 数据截至: {meta['as_of']} | 生成时间: {meta['generated_at']}")
    lines.append("")

    summary = report["summary"]
    lines.append("## 账户摘要")
    lines.append(f"- 总资产: **{summary['total_assets']:.2f}** 元")
    lines.append(f"- 今日盈亏: **{summary['today_pnl']:.2f}** 元")
    lines.append(f"- 基金: {summary['fund_assets']:.2f} 元 | 股票: {summary['stock_assets']:.2f} 元 (可用现金 {summary['stock_cash']:.2f})")
    lines.append(f"- 今日触发操作: {summary['actionable_count']} 条")
    lines.append("")

    review = report["今日复盘"]
    lines.append("## 今日复盘")
    lines.append(review["账户表现"])
    lines.append("")
    if review["规则触发"]:
        lines.append("**规则触发:**")
        for item in review["规则触发"]:
            lines.append(f"- {item}")
    else:
        lines.append("**规则触发:** 无")
    lines.append("")
    lines.append(f"**Agent综合摘要:** {review['Agent综合摘要']}")
    lines.append("")

    signals = report["持仓信号"]
    if signals["技术分析"]:
        lines.append("## 技术分析信号")
        for item in signals["技术分析"]:
            lines.append(f"- {item}")
        lines.append("")

    risks = report["风险提示"]
    if risks:
        lines.append("## 风险提示")
        for item in risks:
            lines.append(f"- ⚠️ {item}")
        lines.append("")

    plans = report["明日计划"]
    lines.append("## 明日计划")
    for item in plans:
        lines.append(f"- {item}")

    return "\n".join(lines)


def save_daily_report(report: dict[str, Any], directory: str | Path = "reports") -> Path:
    """Save the daily report as JSON and Markdown."""
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    date_str = report["meta"]["date"]
    json_path = dir_path / f"report_{date_str}.json"
    md_path = dir_path / f"report_{date_str}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path.write_text(render_report_markdown(report), encoding="utf-8")

    return md_path
