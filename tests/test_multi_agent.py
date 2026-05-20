import pandas as pd

from quant_assistant.config import load_json
from quant_assistant.multi_agent import _data_agent, _risk_agent


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


def test_risk_agent_does_not_mark_short_term_fallback_positions_as_uncovered():
    config = load_json("config.json")
    portfolio = load_json("portfolio.json")

    report = _risk_agent(config, portfolio, quotes={})

    uncovered_messages = [item for item in report.findings if item.startswith("无策略覆盖:")]
    assert uncovered_messages == []
