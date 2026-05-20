from __future__ import annotations

from typing import Any

from .strategy import position_strategy_tag

def build_llm_context(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    recommendations: list[dict[str, str]],
    quotes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a rich context object for LLM consumption.

    Returns a dict with account summary, position details, rule-engine
    recommendations, and derived signals (cash stress, concentration, etc.).
    """
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]

    fund_positions = fund.get("positions", [])
    stock_positions = stock.get("positions", [])

    total_assets = fund.get("total_assets", 0) + stock.get("total_assets", 0)
    stock_mv = stock.get("market_value", 0)
    stock_cash = stock.get("available_cash", 0)

    # Concentration: largest single stock position
    stock_by_mv = sorted(stock_positions, key=lambda p: p.get("market_value", 0), reverse=True)
    top_stock = stock_by_mv[0] if stock_by_mv else None
    concentration_pct = (top_stock["market_value"] / stock_mv * 100) if top_stock and stock_mv else 0

    # Uncovered positions (tag=imported or no strategy binding)
    uncovered = [
        {
            "name": p["name"],
            "tag": position_strategy_tag(config, p, "stock") or p.get("tag", "unknown"),
            "market_value": p.get("market_value", 0),
            "holding_pnl_pct": p.get("holding_pnl_pct", 0),
            "shares": p.get("shares", 0),
            "price": p.get("price", 0),
            "cost": p.get("cost", 0),
        }
        for p in stock_positions
        if position_strategy_tag(config, p, "stock") == "imported"
    ]

    # Cash stress signal
    cash_stress = stock_cash < 100

    # Action summary
    actions = {a["action"] for a in recommendations}
    sell_recs = [a for a in recommendations if a["action"] == "SELL"]
    buy_recs = [a for a in recommendations if a["action"] == "BUY"]
    hold_recs = [a for a in recommendations if a["action"] == "HOLD"]

    return {
        "total_assets": round(total_assets, 2),
        "fund": {
            "total_assets": round(fund.get("total_assets", 0), 2),
            "today_pnl": round(fund.get("today_pnl", 0), 2),
            "position_count": len(fund_positions),
        },
        "stock": {
            "total_assets": round(stock.get("total_assets", 0), 2),
            "market_value": round(stock_mv, 2),
            "available_cash": round(stock_cash, 2),
            "today_pnl": round(stock.get("today_pnl", 0), 2),
            "holding_pnl": round(stock.get("holding_pnl", 0), 2),
            "position_count": len(stock_positions),
        },
        "concentration": {
            "top_name": top_stock["name"] if top_stock else None,
            "top_market_value": top_stock["market_value"] if top_stock else 0,
            "concentration_pct": round(concentration_pct, 2),
        },
        "cash_stress": cash_stress,
        "uncovered_positions": uncovered,
        "recommendations": {
            "sell": sell_recs,
            "buy": buy_recs,
            "hold": hold_recs,
        },
        "quotes": quotes or {},
    }


def generate_llm_prompt(ctx: dict[str, Any]) -> str:
    """Generate a structured prompt for the LLM advisor.

    The prompt asks the LLM to produce a concise, actionable daily
    briefing in Chinese.
    """
    lines = [
        "你是一位理性的量化投资助手。请根据以下账户数据和规则引擎输出，生成今日操作建议。",
        "",
        "要求：",
        "1. 先给出一句话摘要（今天要不要操作、操作什么）。",
        "2. 再分条列出每个需要关注的持仓，说明理由。",
        "3. 对无策略覆盖的持仓，给出风险提示（止损建议、仓位集中度等）。",
        "4. 如果现金紧张，明确指出。",
        "5. 语气直接、具体，不要空话。",
        "",
        "=== 账户概览 ===",
        f"总资产: {ctx['total_assets']:.2f} 元",
        f"基金: {ctx['fund']['total_assets']:.2f} 元 (今日盈亏 {ctx['fund']['today_pnl']:.2f})",
        f"股票: {ctx['stock']['total_assets']:.2f} 元 (市值 {ctx['stock']['market_value']:.2f}, 可用现金 {ctx['stock']['available_cash']:.2f}, 今日盈亏 {ctx['stock']['today_pnl']:.2f})",
        "",
    ]

    if ctx["cash_stress"]:
        lines.append("⚠️ 现金紧张: 股票可用现金不足 100 元，买入能力极弱。")
        lines.append("")

    conc = ctx["concentration"]
    if conc["concentration_pct"] > 30:
        lines.append(
            f"⚠️ 仓位集中: {conc['top_name']} 占股票市值 {conc['concentration_pct']:.1f}%，"
            f"市值 {conc['top_market_value']:.2f} 元。"
        )
        lines.append("")

    if ctx["uncovered_positions"]:
        lines.append("=== 无策略覆盖持仓（需人工关注） ===")
        for p in ctx["uncovered_positions"]:
            lines.append(
                f"- {p['name']}: 市值 {p['market_value']:.2f}, "
                f"盈亏 {p['holding_pnl_pct']:.2f}%, 成本 {p['cost']:.3f}, 现价 {p['price']:.3f}"
            )
        lines.append("")

    recs = ctx["recommendations"]
    if recs["sell"]:
        lines.append("=== 规则引擎卖出建议 ===")
        for r in recs["sell"]:
            lines.append(f"- {r['instrument']}: {r['amount']} — {r['reason']}")
        lines.append("")

    if recs["buy"]:
        lines.append("=== 规则引擎买入建议 ===")
        for r in recs["buy"]:
            lines.append(f"- {r['instrument']}: {r['amount']} — {r['reason']}")
        lines.append("")

    lines.append("=== 规则引擎 HOLD 列表 ===")
    for r in recs["hold"]:
        lines.append(f"- {r['instrument']}: {r['reason']}")

    lines.append("")
    lines.append("请生成中文操作建议：")

    return "\n".join(lines)


def generate_advice(ctx: dict[str, Any]) -> dict[str, Any]:
    """Generate LLM advice, either via API or fallback to prompt-only.

    Returns {"mode": "api", "text": "...", "usage": {...}} or
            {"mode": "prompt", "text": "(未配置API)", "prompt": "..."}
    """
    from .llm_client import call_llm, is_configured

    prompt = generate_llm_prompt(ctx)

    if is_configured():
        result = call_llm(prompt)
        if result["ok"]:
            return {"mode": "api", "text": result["text"], "usage": result.get("usage", {})}
        return {"mode": "api_error", "text": f"API 调用失败: {result['error']}", "prompt": prompt}

    return {"mode": "prompt", "text": "(未配置 DeepSeek API Key，请复制下方 prompt 到 Kimi/DeepSeek 获取建议)", "prompt": prompt}


def parse_llm_response(text: str) -> dict[str, Any]:
    """Parse LLM response into structured sections.

    Returns dict with 'summary', 'actions', 'risks' keys.
    This is a lightweight parser; callers may refine.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    summary = ""
    actions: list[dict[str, str]] = []
    risks: list[str] = []

    current_section = "summary"
    for line in lines:
        lower = line.lower()
        if "摘要" in line or "总结" in line or "一句话" in line:
            current_section = "summary"
            continue
        if any(k in lower for k in ("卖出", "买入", "操作", "建议", "action")):
            current_section = "actions"
            continue
        if any(k in lower for k in ("风险", "注意", "提示", "⚠️", "warning")):
            current_section = "risks"
            continue

        if current_section == "summary":
            summary += line + " "
        elif current_section == "actions":
            actions.append({"text": line})
        elif current_section == "risks":
            risks.append(line)

    return {
        "summary": summary.strip(),
        "actions": actions,
        "risks": risks,
        "raw": text,
    }
