import pandas as pd

from quant_assistant.recommendation_view import (
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


def test_strategy_coverage_flags_imported_holding():
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

    assert len(issues) == 1
    assert issues[0]["标的"] == "沃尔核材"
    assert issues[0]["问题"] == "缺少策略标签"


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
