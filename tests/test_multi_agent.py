import pandas as pd

from quant_assistant.config import load_json
from quant_assistant.multi_agent import _data_agent, _decision_agent, _risk_agent


def test_data_agent_does_not_flag_snapshot_only_healthcare_proxy_as_missing(monkeypatch):
    config = load_json("config.json")
    portfolio = load_json("portfolio.json")

    monkeypatch.setattr(
        "quant_assistant.multi_agent.scan_etfs",
        lambda top_n=10: (pd.DataFrame([{"名称": "示例ETF"}]), ["mocked"]),
    )

    report = _data_agent(config, portfolio, quotes={}, scan_top_n=10)

    missing_messages = [item for item in report.findings if item.startswith("行情缺失:")]
    assert missing_messages
    assert "创新药" not in missing_messages[0]


def test_data_agent_skips_malformed_accounts_and_positions(monkeypatch):
    config = {"rules": {"short_term": {}}, "quotes": {"proxies": {"半导体": "1.000001"}}}
    portfolio = {
        "accounts": {
            "bad": "not-an-account",
            "stock": {
                "positions": [
                    "not-a-position",
                    {"name": "Bad OCR", "tag": "imported", "shares": "bad", "price": "bad", "market_proxy": "半导体"},
                ]
            },
        }
    }

    monkeypatch.setattr(
        "quant_assistant.multi_agent.scan_etfs",
        lambda top_n=10: (pd.DataFrame(), ["mocked"]),
    )

    report = _data_agent(config, portfolio, quotes={}, scan_top_n=10)

    assert report.status in {"ok", "warn"}
    assert report.data["scan_messages"] == ["mocked"]


def test_decision_agent_handles_bad_available_cash(monkeypatch):
    monkeypatch.setattr(
        "quant_assistant.multi_agent.generate_recommendations",
        lambda config, portfolio, quotes: [
            {"action": "BUY", "instrument": "Test", "amount": "100 股", "reason": "mock"},
        ],
    )
    portfolio = {"accounts": {"stock": {"available_cash": "bad"}}}

    report = _decision_agent({}, portfolio, quotes={})

    assert report.status == "ok"
    assert any("0.00" in finding for finding in report.findings)


def test_decision_agent_tolerates_bad_recommendation_shapes(monkeypatch):
    monkeypatch.setattr(
        "quant_assistant.multi_agent.generate_recommendations",
        lambda config, portfolio, quotes: [
            "bad",
            {"action": "BUY"},
            {"action": "SELL", "instrument": "Test", "amount": "100", "reason": "mock"},
        ],
    )

    report = _decision_agent({}, {"accounts": {"stock": {"available_cash": 1000}}}, quotes={})

    assert report.status == "ok"
    assert report.data["actionable_count"] == 1
    assert any("SELL Test 100" in finding for finding in report.findings)


def test_risk_agent_does_not_mark_short_term_fallback_positions_as_uncovered():
    config = load_json("config.json")
    portfolio = load_json("portfolio.json")

    report = _risk_agent(config, portfolio, quotes={})

    uncovered_messages = [item for item in report.findings if item.startswith("无策略覆盖:")]
    assert uncovered_messages == []


def test_risk_agent_handles_bad_numeric_values():
    config = {"rules": {"short_term": {}}}
    portfolio = {
        "accounts": {
            "fund": {
                "positions": [
                    "not-a-position",
                    {"name": "Bad Fund", "holding_pnl_pct": "bad"},
                    {"name": "Deep Fund", "holding_pnl_pct": "-12"},
                ]
            },
            "stock": {
                "available_cash": "bad",
                "market_value": "100",
                "positions": [
                    {"name": "Top", "tag": "short_term", "market_value": "80"},
                    {"name": "Bad OCR", "tag": "imported", "market_value": "bad", "shares": "bad", "price": "bad"},
                ],
            },
        }
    }

    report = _risk_agent(config, portfolio, quotes={})

    assert report.data["cash_stress"] is True
    assert report.data["top_name"] == "Top"
    assert report.data["top_concentration_pct"] == 80.0
    assert report.data["uncovered"] == ["Bad OCR"]
    assert any("Deep Fund" in finding for finding in report.findings)
