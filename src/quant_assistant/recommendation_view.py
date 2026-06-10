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
BUILT_IN_KNOWN_TAGS = {"core_ai_dca"}


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


def _clean_display_name(raw: str) -> str:
    """Strip strategy tags accidentally appended to position names."""
    name = raw.strip()
    for suffix in ("·wide_index", "wide_index", "·tactical_ai", "tactical_ai",
                   "·power_grid", "power_grid", "·military", "military",
                   "·semiconductor", "semiconductor", "·robot", "robot",
                   "·overseas", "overseas", "·healthcare", "healthcare",
                   "·defensive", "defensive", "·core_ai_dca", "core_ai_dca",
                   "·imported", "imported"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].rstrip("· ").strip()
            break
    return name or raw


TAG_DISPLAY = {
    "wide_index": "宽基",
    "tactical_ai": "AI战术",
    "power_grid": "电网",
    "military": "军工",
    "semiconductor": "半导体",
    "robot": "机器人",
    "overseas": "海外",
    "healthcare": "医药",
    "defensive": "防御",
    "core_ai_dca": "AI定投",
    "imported": "未分类",
}


def fund_holdings_table(portfolio: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    account = _account(portfolio, "fund")
    for position in _positions(account):
        rows.append(
            {
                "基金名称": _clean_display_name(position.get("name", "")),
                "市值": position.get("market_value"),
                "当日涨跌%": position.get("last_daily_pct"),
                "持有收益": position.get("holding_pnl"),
                "持有收益%": position.get("holding_pnl_pct"),
                "关联指数": position.get("market_proxy"),
                "策略": TAG_DISPLAY.get(position.get("tag", ""), position.get("tag", "")),
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


_CASH_SUMMARY_NAMES = {"可用转账", "可用资金", "可用", "资金", "现金", "可用余额"}


def stock_holdings_table(portfolio: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    account = _account(portfolio, "stock")
    for position in _positions(account):
        name = str(position.get("name", "")).strip()
        if name in _CASH_SUMMARY_NAMES:
            continue
        rows.append(
            {
                "股票/基金": _clean_display_name(name),
                "市值": position.get("market_value"),
                "持股": position.get("shares"),
                "现价": position.get("price"),
                "成本": position.get("cost"),
                "持仓盈亏": position.get("holding_pnl"),
                "持仓收益%": position.get("holding_pnl_pct"),
                "关联指数": position.get("market_proxy"),
                "策略": TAG_DISPLAY.get(position.get("tag", ""), position.get("tag", "")),
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
    rules = _mapping(config.get("rules"))
    bindings = _mapping(config.get("strategy_bindings"))
    known_tags = set(rules) | set(bindings) | BUILT_IN_KNOWN_TAGS
    quotes = _mapping(config.get("quotes"))
    proxies = _mapping(quotes.get("proxies"))
    issues: list[dict[str, str]] = []

    for account_key, account in _mapping(portfolio.get("accounts")).items():
        if not isinstance(account, dict):
            continue
        account_label = "股票" if account_key == "stock" else "基金" if account_key == "fund" else account_key
        for position in _positions(account):
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


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _account(portfolio: dict[str, Any], account_key: str) -> dict[str, Any]:
    account = _mapping(portfolio.get("accounts")).get(account_key, {})
    return account if isinstance(account, dict) else {}


def _positions(account: dict[str, Any]) -> list[dict[str, Any]]:
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        return []
    return [position for position in positions if isinstance(position, dict)]
