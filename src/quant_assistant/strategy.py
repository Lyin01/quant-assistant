from __future__ import annotations

from typing import Any

from .data_provider import Quote, quote_for_proxy


Recommendation = dict[str, str]


def generate_recommendations(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote] | None = None,
    data_source_health: dict[str, dict[str, float]] | None = None,
    is_trading_day: bool = True,
) -> list[Recommendation]:
    quotes = quotes or {}
    recommendations: list[Recommendation] = []
    _prepend_health_warning(recommendations, data_source_health)
    _prepend_trading_day_notice(recommendations, is_trading_day, quotes)
    recommendations.extend(_fund_recommendations(config, portfolio, quotes))
    recommendations.extend(_stock_recommendations(config, portfolio, quotes))
    return recommendations


def _prepend_health_warning(
    recs: list[Recommendation],
    health: dict[str, dict[str, float]] | None,
) -> None:
    """Prepend a global warning if data sources show poor reliability."""
    if not health:
        return
    shaky = []
    for provider, stats in health.items():
        rate = stats.get("success_rate", 100)
        total = stats.get("total_requests", 0)
        if total >= 5 and rate < 80:
            shaky.append(f"{provider} 成功率 {rate:.0f}%")
    if shaky:
        recs.append({
            "action": "⚠️",
            "instrument": "数据源异常",
            "amount": "",
            "reason": "以下数据源近期成功率偏低，建议核对行情准确性："
                       + "；".join(shaky),
        })


def _prepend_trading_day_notice(
    recs: list[Recommendation],
    is_trading_day: bool,
    quotes: dict[str, Quote],
) -> None:
    """Prepend a notice when the market is closed."""
    if is_trading_day:
        return
    if quotes:
        recs.append({
            "action": "ℹ️",
            "instrument": "非交易日",
            "amount": "",
            "reason": "今天不是交易日，行情为上一交易日数据，买卖清单仅作提前规划参考。",
        })
    else:
        recs.append({
            "action": "ℹ️",
            "instrument": "非交易日",
            "amount": "",
            "reason": "今天不是交易日，且未获取到实时行情，买卖清单仅供参考。",
        })


def _prepend_health_warning(
    recs: list[Recommendation],
    health: dict[str, dict[str, float]] | None,
) -> None:
    """Prepend a global warning if data sources show poor reliability."""
    if not health:
        return
    shaky = []
    for provider, stats in health.items():
        rate = stats.get("success_rate", 100)
        total = stats.get("total_requests", 0)
        if total >= 5 and rate < 80:
            shaky.append(f"{provider} 成功率 {rate:.0f}%")
    if shaky:
        recs.append({
            "action": "⚠️",
            "instrument": "数据源异常",
            "amount": "",
            "reason": "以下数据源近期成功率偏低，建议核对行情准确性："
                       + "；".join(shaky),
        })


def _fund_recommendations(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> list[Recommendation]:
    rules = config["rules"]
    cash = config["cash_plan"]
    fund = portfolio["accounts"]["fund"]
    positions = fund.get("positions", [])
    recs: list[Recommendation] = []

    actual_cash = float(portfolio.get("accounts", {}).get("stock", {}).get("available_cash", 0) or 0)
    planned_cash = float(cash.get("available_cash_total", 0) or 0)
    available_cash = max(actual_cash, planned_cash)
    minimum_cash = float(cash.get("minimum_cash_reserve", 0))
    deployable_cash = max(0, available_cash - minimum_cash)

    for position in positions:
        tag = position.get("tag")
        name = position["name"]
        daily_pct = _daily_pct(config, quotes, position)
        profit_pct = float(position.get("holding_pnl_pct", 0))
        warn = _data_warning(config, quotes, position)

        # Built-in logic per tag — no template layer, config.json only has thresholds
        if tag == "core_ai_dca":
            recs.append(_hold(name, "长期定投仓，不按短线波动处理。"))

        elif tag == "tactical_ai":
            rule = rules["tactical_ai"]
            if daily_pct >= rule["sell_daily_pct"] and profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_money(name, rule["sell_amount"], f"AI 大仓涨幅 {daily_pct:.2f}%，持有收益 {profit_pct:.2f}%，触发止盈。"))
            elif daily_pct <= rule["buy_pullback_pct"] and deployable_cash >= rule["buy_amount"]:
                recs.append(_buy_money(name, rule["buy_amount"], f"AI 回撤 {daily_pct:.2f}%，触发小额低吸。"))
            else:
                recs.append(_hold(name, f"AI 大仓未触发买卖条件，当前参考涨跌 {daily_pct:.2f}%。 {warn}" if warn else f"AI 大仓未触发买卖条件，当前参考涨跌 {daily_pct:.2f}%。"))

        elif tag == "power_grid":
            rule = rules["power_grid"]
            if daily_pct >= rule["sell_daily_pct"] and profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_money(name, rule["sell_amount"], f"电网涨幅 {daily_pct:.2f}%，持有收益 {profit_pct:.2f}%，仓位仍偏主题，卖出降波动。"))
            else:
                recs.append(_hold(name, f"电网未触发继续止盈条件，当前参考涨跌 {daily_pct:.2f}%。 {warn}" if warn else f"电网未触发继续止盈条件，当前参考涨跌 {daily_pct:.2f}%。"))

        elif tag == "military":
            rule = rules["military"]
            if profit_pct >= rule["sell_profit_pct"] and daily_pct >= 0:
                recs.append(_sell_money(name, rule["sell_amount"], f"军工已从亏损修复到 {profit_pct:.2f}%，按规则反弹后降低暴露。"))
            else:
                recs.append(_hold(name, "军工不补仓；等待反弹修复后再减。"))

        elif tag == "overseas":
            rule = rules["overseas"]
            if daily_pct >= rule["sell_daily_pct"] and profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_money(name, rule["sell_amount"], f"海外涨幅 {daily_pct:.2f}%，持有收益 {profit_pct:.2f}%，止盈降仓。"))
            else:
                recs.append(_hold(name, f"海外未触发止盈，当前参考涨跌 {daily_pct:.2f}%，收益 {profit_pct:.2f}%。 {warn}" if warn else f"海外未触发止盈，当前参考涨跌 {daily_pct:.2f}%，收益 {profit_pct:.2f}%。"))

        elif tag == "defensive":
            rule = rules["defensive"]
            if profit_pct >= rule["rebalance_profit_pct"]:
                recs.append(_sell_money(name, 200, f"稳健收益 {profit_pct:.2f}%，可适当止盈转为子弹。"))
            else:
                recs.append(_hold(name, f"稳健仓位收益 {profit_pct:.2f}%，继续持有。 {warn}" if warn else f"稳健仓位收益 {profit_pct:.2f}%，继续持有。"))

        elif tag == "healthcare":
            rule = rules.get("healthcare", {})
            if profit_pct >= rule.get("sell_profit_pct", 10.0):
                recs.append(_sell_money(name, 200, f"医药持仓收益 {profit_pct:.2f}%，触发止盈。"))
            else:
                recs.append(_hold(name, f"医药持仓收益 {profit_pct:.2f}%，未触发止盈。 {warn}" if warn else f"医药持仓收益 {profit_pct:.2f}%，未触发止盈。"))

        else:
            recs.append(_hold(name, "无特定策略规则，观望。"))

    wide_rule = rules["wide_index"]
    wide_positions = [p for p in positions if p.get("tag") == "wide_index"]
    if deployable_cash > 0 and available_cash >= wide_rule["deploy_when_cash_above"] and wide_positions:
        candidate = min(wide_positions, key=lambda item: _daily_pct(config, quotes, item))
        candidate_pct = _daily_pct(config, quotes, candidate)
        if candidate_pct <= wide_rule["daily_pct_max_for_buy"]:
            amount = wide_rule["strong_buy_amount"] if candidate_pct <= wide_rule["daily_pct_strong_buy"] else wide_rule["normal_buy_amount"]
            recs.insert(0, _buy_money(candidate["name"], amount, f"现金较多，宽基参考涨跌 {candidate_pct:.2f}%，允许回补底仓。"))

    return recs


def _stock_recommendations(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    quotes: dict[str, Quote],
) -> list[Recommendation]:
    rules = config["rules"]
    stock = portfolio["accounts"]["stock"]
    recs: list[Recommendation] = []

    for position in stock.get("positions", []):
        tag = position.get("tag")
        name = position["name"]
        price = _price(config, quotes, position)
        shares = int(position.get("shares", 0))
        profit_pct = _profit_pct(config, quotes, position)
        warn = _data_warning(config, quotes, position)

        # Built-in logic per tag — no template layer
        if tag == "semiconductor":
            rule = rules["semiconductor"]
            if shares < rule["max_position_shares"] and price <= rule["limit_buy_price"]:
                recs.append(_buy_shares(name, rule["limit_buy_shares"], f"半导体现价 {price:.3f} 小于等于挂单价 {rule['limit_buy_price']:.3f}，允许补一手。"))
            elif price <= rule["stop_chasing_price"]:
                recs.append(_limit_buy(name, rule["limit_buy_shares"], rule["limit_buy_price"], f"半导体现价 {price:.3f} 接近计划价；只在 {rule['limit_buy_price']:.3f} 附近或以下买。"))
            else:
                recs.append(_hold(name, f"半导体价格 {price:.3f} 高于追价上限，不买。 {warn}" if warn else f"半导体价格 {price:.3f} 高于追价上限，不买。"))

        elif tag == "robot":
            rule = rules["robot"]
            if profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_shares(name, rule["sell_shares"], f"机器人持有收益 {profit_pct:.2f}%，触发止盈。"))
            elif rule["pullback_buy_price_low"] <= price <= rule["pullback_buy_price_high"]:
                recs.append(_buy_shares(name, rule["pullback_buy_shares"], f"机器人回到 {price:.3f}，处于计划低吸区间。"))
            else:
                recs.append(_hold(name, f"机器人持有收益 {profit_pct:.2f}%，未触发买卖。 {warn}" if warn else f"机器人持有收益 {profit_pct:.2f}%，未触发买卖。"))

        elif tag == "healthcare":
            rule = rules["healthcare"]
            if profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_shares(name, rule["sell_shares"], f"创新药收益 {profit_pct:.2f}%，触发止盈。"))
            else:
                recs.append(_hold(name, f"创新药收益 {profit_pct:.2f}%，未触发止盈。 {warn}" if warn else f"创新药收益 {profit_pct:.2f}%，未触发止盈。"))

        elif tag == "overseas":
            rule = rules["overseas"]
            if profit_pct >= rule["sell_profit_pct"]:
                recs.append(_sell_shares(name, 100, f"海外持仓收益 {profit_pct:.2f}%，止盈。"))
            else:
                recs.append(_hold(name, f"海外持仓收益 {profit_pct:.2f}%，继续持有。 {warn}" if warn else f"海外持仓收益 {profit_pct:.2f}%，继续持有。"))

        else:
            market_value = float(position.get("market_value", 0) or 0)
            if market_value >= 500:
                recs.append(_hold(name, f"当前无对应策略规则（tag={tag}），持仓市值 {market_value:.0f} 元，请考虑补充策略配置。 {warn}" if warn else f"当前无对应策略规则（tag={tag}），持仓市值 {market_value:.0f} 元，请考虑补充策略配置。"))
            else:
                recs.append(_hold(name, "仓位小或无明确信号，不操作。"))

    return recs


def _daily_pct(config: dict[str, Any], quotes: dict[str, Quote], position: dict[str, Any]) -> float:
    use_live = bool(config.get("market_provider", {}).get("use_live_proxy_for_decisions", False))
    if not use_live:
        return float(position.get("last_daily_pct", 0))

    quote = quote_for_proxy(position.get("market_proxy"), config, quotes)
    if quote and quote.pct is not None:
        return float(quote.pct)
    return float(position.get("last_daily_pct", 0))


def _price(config: dict[str, Any], quotes: dict[str, Quote], position: dict[str, Any]) -> float:
    use_live = bool(config.get("market_provider", {}).get("use_live_proxy_for_decisions", False))
    if use_live:
        quote = quote_for_proxy(position.get("market_proxy"), config, quotes)
        if quote and quote.price is not None:
            return float(quote.price)
    return float(position.get("price", 0))


def _profit_pct(config: dict[str, Any], quotes: dict[str, Quote], position: dict[str, Any]) -> float:
    # Prefer broker-provided holding_pnl_pct — it includes dividends and fees.
    broker_pnl = position.get("holding_pnl_pct")
    if broker_pnl is not None:
        try:
            return float(broker_pnl)
        except (TypeError, ValueError):
            pass
    # Fallback: estimate from price/cost (ignores dividends but better than nothing).
    price = _price(config, quotes, position)
    cost = float(position.get("cost", 0) or 0)
    if price > 0 and cost > 0:
        return (price / cost - 1) * 100
    return 0.0


def _live_data_missing(config: dict[str, Any], quotes: dict[str, Quote], position: dict[str, Any]) -> bool:
    """Check if live data is configured but unavailable for this position."""
    use_live = bool(config.get("market_provider", {}).get("use_live_proxy_for_decisions", False))
    if not use_live:
        return False
    proxy = position.get("market_proxy")
    if not proxy:
        return True
    quote = quote_for_proxy(proxy, config, quotes)
    return quote is None or quote.pct is None


def _data_warning(config: dict[str, Any], quotes: dict[str, Quote], position: dict[str, Any]) -> str:
    """Return a warning suffix if live data is expected but unavailable."""
    if not _live_data_missing(config, quotes, position):
        return ""
    return "（实时行情缺失，参考值为持仓快照）"


def _buy_money(instrument: str, amount: float | int, reason: str) -> Recommendation:
    return {"action": "BUY", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}


def _sell_money(instrument: str, amount: float | int, reason: str) -> Recommendation:
    return {"action": "SELL", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}


def _buy_shares(instrument: str, shares: int, reason: str) -> Recommendation:
    return {"action": "BUY", "instrument": instrument, "amount": f"{shares} 股", "reason": reason}


def _sell_shares(instrument: str, shares: int, reason: str) -> Recommendation:
    return {"action": "SELL", "instrument": instrument, "amount": f"{shares} 股", "reason": reason}


def _limit_buy(instrument: str, shares: int, price: float, reason: str) -> Recommendation:
    return {"action": "LIMIT_BUY", "instrument": instrument, "amount": f"{shares} 股 @ {price:.3f}", "reason": reason}


def _hold(instrument: str, reason: str) -> Recommendation:
    return {"action": "HOLD", "instrument": instrument, "amount": "-", "reason": reason}
