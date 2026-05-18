from __future__ import annotations

from typing import Any

import pandas as pd


ACTIONABLE_ACTIONS = {"BUY", "SELL", "LIMIT_BUY"}
PROXY_REQUIRED_TAGS = {
    "wide_index",
    "tactical_ai",
    "core_ai_dca",
    "power_grid",
    "military",
    "semiconductor",
    "robot",
    "overseas",
    "healthcare",
}


def split_recommendations(
    recommendations: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    actionable: list[dict[str, str]] = []
    watchlist: list[dict[str, str]] = []
    for recommendation in recommendations:
        if recommendation.get("action") in ACTIONABLE_ACTIONS:
            actionable.append(recommendation)
        else:
            watchlist.append(recommendation)
    return actionable, watchlist


def recommendation_table(recommendations: list[dict[str, str]], data_source: str) -> pd.DataFrame:
    rows = [
        {
            "动作": recommendation.get("action", ""),
            "标的": recommendation.get("instrument", ""),
            "数量/金额": recommendation.get("amount", ""),
            "数据来源": data_source,
            "原因": recommendation.get("reason", ""),
        }
        for recommendation in recommendations
    ]
    return pd.DataFrame(rows, columns=["动作", "标的", "数量/金额", "数据来源", "原因"])


def fund_holdings_table(portfolio: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    account = portfolio.get("accounts", {}).get("fund", {})
    for position in account.get("positions", []):
        rows.append(
            {
                "基金名称": position.get("name", ""),
                "市值": position.get("market_value"),
                "当日涨跌%": position.get("last_daily_pct"),
                "持有收益": position.get("holding_pnl"),
                "持有收益%": position.get("holding_pnl_pct"),
                "关联指数": position.get("market_proxy"),
                "策略": position.get("tag", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "基金名称",
            "市值",
            "当日涨跌%",
            "持有收益",
            "持有收益%",
            "关联指数",
            "策略",
        ],
    )


def stock_holdings_table(portfolio: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    account = portfolio.get("accounts", {}).get("stock", {})
    for position in account.get("positions", []):
        rows.append(
            {
                "股票/基金": position.get("name", ""),
                "市值": position.get("market_value"),
                "持股": position.get("shares"),
                "现价": position.get("price"),
                "成本": position.get("cost"),
                "持仓盈亏": position.get("holding_pnl"),
                "持仓收益%": position.get("holding_pnl_pct"),
                "关联指数": position.get("market_proxy"),
                "策略": position.get("tag", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "股票/基金",
            "市值",
            "持股",
            "现价",
            "成本",
            "持仓盈亏",
            "持仓收益%",
            "关联指数",
            "策略",
        ],
    )


def strategy_coverage_issues(config: dict[str, Any], portfolio: dict[str, Any]) -> list[dict[str, str]]:
    rules = config.get("rules", {})
    bindings = config.get("strategy_bindings", {})
    known_tags = set(rules) | set(bindings)
    proxies = config.get("quotes", {}).get("proxies", {})
    issues: list[dict[str, str]] = []

    for account_key, account in portfolio.get("accounts", {}).items():
        account_label = "股票" if account_key == "stock" else "基金" if account_key == "fund" else account_key
        for position in account.get("positions", []):
            name = str(position.get("name", "")).strip()
            if not name:
                continue
            tag = str(position.get("tag", "")).strip()
            proxy_name = position.get("market_proxy")

            if not tag:
                issues.append(
                    _issue(
                        account_label,
                        name,
                        "缺少策略标签",
                        "选择合适的 tag，或确认它只作为观察仓位。",
                    )
                )
                continue

            # imported 是有意为之的未分类占位符，不再提示为问题
            if tag == "imported":
                continue

            if tag not in known_tags:
                issues.append(
                    _issue(
                        account_label,
                        name,
                        "未知策略标签",
                        f"在 config.json 的 rules 或 strategy_bindings 中补充 `{tag}`。",
                    )
                )

            if tag in PROXY_REQUIRED_TAGS and not proxy_name:
                issues.append(
                    _issue(
                        account_label,
                        name,
                        "缺少行情代理",
                        "为该持仓补充 market_proxy，或确认策略只按持仓快照判断。",
                    )
                )
            elif proxy_name and proxy_name not in proxies:
                issues.append(
                    _issue(
                        account_label,
                        name,
                        "行情代理未配置",
                        f"在 config.json 的 quotes.proxies 中补充 `{proxy_name}`。",
                    )
                )

    return issues


def _issue(account: str, instrument: str, problem: str, suggestion: str) -> dict[str, str]:
    return {
        "级别": "提示",
        "账户": account,
        "标的": instrument,
        "问题": problem,
        "建议": suggestion,
    }
