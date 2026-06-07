import pandas as pd

from quant_assistant.recommendation_view import (
    fund_holdings_table,
    recommendation_table,
    split_recommendations,
    strategy_coverage_issues,
    stock_holdings_table,
)


def test_split_recommendations_keeps_actionable_items_first():
    recommendations = [
        {"action": "HOLD", "instrument": "A", "amount": "—", "reason": "watch"},
        {"action": "BUY", "instrument": "B", "amount": "100 元", "reason": "buy"},
        {"action": "LIMIT_BUY", "instrument": "C", "amount": "100 股 @ 2.000", "reason": "limit"},
        {"action": "SELL", "instrument": "D", "amount": "500 元", "reason": "sell"},
    ]

    actionable, watchlist = split_recommendations(recommendations)

    assert [item["instrument"] for item in actionable] == ["B", "C", "D"]
    assert [item["instrument"] for item in watchlist] == ["A"]


def test_recommendation_table_includes_data_source():
    recommendations = [
        {"action": "BUY", "instrument": "半导体", "amount": "100 股", "reason": "低吸"},
    ]

    frame = recommendation_table(recommendations, data_source="实时行情")

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["动作", "标的", "数量/金额", "数据来源", "原因"]
    assert frame.loc[0, "数据来源"] == "实时行情"
    assert frame.loc[0, "标的"] == "半导体"


def test_fund_holdings_table_uses_fund_specific_columns():
    portfolio = {
        "accounts": {
            "fund": {
                "positions": [
                    {
                        "name": "易方达中证500",
                        "tag": "wide_index",
                        "market_value": 5510.16,
                        "holding_pnl": -161.14,
                        "holding_pnl_pct": -2.84,
                        "market_proxy": "中证500",
                        "last_daily_pct": 0.22,
                    }
                ]
            },
        }
    }

    frame = fund_holdings_table(portfolio)

    assert list(frame.columns) == [
        "基金名称",
        "市值",
        "当日涨跌%",
        "持有收益",
        "持有收益%",
        "关联指数",
        "策略",
    ]
    assert frame.loc[0, "基金名称"] == "易方达中证500"
    assert frame.loc[0, "当日涨跌%"] == 0.22
    assert frame.loc[0, "关联指数"] == "中证500"


def test_stock_holdings_table_uses_stock_specific_columns():
    portfolio = {
        "accounts": {
            "stock": {
                "positions": [
                    {
                        "name": "半导体",
                        "tag": "semiconductor",
                        "market_value": 207.7,
                        "holding_pnl": 0.6,
                        "holding_pnl_pct": 0.29,
                        "shares": 100,
                        "price": 2.077,
                        "cost": 2.071,
                        "market_proxy": "半导体",
                    }
                ]
            },
        }
    }

    frame = stock_holdings_table(portfolio)

    assert list(frame.columns) == [
        "股票/基金",
        "市值",
        "持股",
        "现价",
        "成本",
        "持仓盈亏",
        "持仓收益%",
        "关联指数",
        "策略",
    ]
    assert frame.loc[0, "股票/基金"] == "半导体"
    assert frame.loc[0, "持股"] == 100
    assert frame.loc[0, "关联指数"] == "半导体"


def test_strategy_coverage_ignores_imported_tag():
    """imported 是有意为之的未分类占位符，不应触发策略覆盖提示。"""
    config = {
        "rules": {"semiconductor": {}},
        "strategy_bindings": {},
        "quotes": {"proxies": {"半导体": "1.512480"}},
    }
    portfolio = {
        "accounts": {
            "stock": {
                "positions": [
                    {"name": "沃尔核材", "tag": "imported", "market_value": 1000},
                ]
            }
        }
    }

    issues = strategy_coverage_issues(config, portfolio)

    assert len(issues) == 0


def test_strategy_coverage_accepts_core_ai_dca_builtin_tag():
    config = {
        "rules": {},
        "strategy_bindings": {},
        "quotes": {"proxies": {"人工智能": "1.515070"}},
    }
    portfolio = {
        "accounts": {
            "fund": {
                "positions": [
                    {
                        "name": "天弘中证人工智能定投小仓",
                        "tag": "core_ai_dca",
                        "market_value": 452.81,
                        "market_proxy": "人工智能",
                    },
                ]
            }
        }
    }

    issues = strategy_coverage_issues(config, portfolio)

    assert issues == []


def test_strategy_coverage_flags_missing_market_proxy_for_live_rule():
    config = {
        "rules": {"healthcare": {}},
        "strategy_bindings": {},
        "quotes": {"proxies": {"创新药": "1.599929"}},
    }
    portfolio = {
        "accounts": {
            "stock": {
                "positions": [
                    {"name": "创新药", "tag": "healthcare", "market_value": 239.4},
                ]
            }
        }
    }

    issues = strategy_coverage_issues(config, portfolio)

    assert len(issues) == 1
    assert issues[0]["问题"] == "缺少行情代理"
    assert "market_proxy" in issues[0]["建议"]


def test_strategy_coverage_flags_unknown_market_proxy():
    config = {
        "rules": {"healthcare": {}},
        "strategy_bindings": {},
        "quotes": {"proxies": {"创新药": "1.599929"}},
    }
    portfolio = {
        "accounts": {
            "stock": {
                "positions": [
                    {
                        "name": "创新药",
                        "tag": "healthcare",
                        "market_proxy": "不存在",
                        "market_value": 239.4,
                    },
                ]
            }
        }
    }

    issues = strategy_coverage_issues(config, portfolio)

    assert len(issues) == 1
    assert issues[0]["问题"] == "行情代理未配置"
    assert "config.json" in issues[0]["建议"]
