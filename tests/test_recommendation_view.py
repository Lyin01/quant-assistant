import pandas as pd

from quant_assistant.recommendation_view import (
    portfolio_holdings_table,
    recommendation_table,
    split_recommendations,
    strategy_coverage_issues,
)


def test_split_recommendations_keeps_actionable_items_first():
    recommendations = [
        {"action": "HOLD", "instrument": "A", "amount": "-", "reason": "watch"},
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


def test_portfolio_holdings_table_flattens_accounts():
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

    frame = portfolio_holdings_table(portfolio)

    assert list(frame.columns) == [
        "账户",
        "标的",
        "策略标签",
        "市值",
        "持仓盈亏",
        "持仓收益%",
        "持股",
        "现价",
        "成本",
        "行情代理",
        "快照涨跌%",
    ]
    assert frame.loc[0, "账户"] == "支付宝基金"
    assert frame.loc[0, "标的"] == "易方达中证500"
    assert frame.loc[1, "账户"] == "国信证券"
    assert frame.loc[1, "持股"] == 100


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
