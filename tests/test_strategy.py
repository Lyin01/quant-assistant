from quant_assistant.config import load_json
from quant_assistant.strategy import generate_recommendations
from quant_assistant.analytics import action_list, add_indicators, backtest_ma_trend, latest_signal
import pandas as pd


def test_strategy_generates_core_actions():
    config = load_json("config.json")
    portfolio = load_json("portfolio.json")

    recs = generate_recommendations(config, portfolio, quotes={})
    text = "\n".join(f"{rec['action']} {rec['instrument']} {rec['amount']}" for rec in recs)

    assert "易方达中证500" in text
    assert "天弘中证电网设备" in text
    assert "广发中证军工ETF联接" in text


def test_analytics_pipeline():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=90, freq="D"),
            "open": range(90),
            "high": range(1, 91),
            "low": range(90),
            "close": [100 + index for index in range(90)],
            "volume": [1000] * 90,
        }
    )

    enriched = add_indicators(frame)
    signal = latest_signal(frame)
    curve, metrics = backtest_ma_trend(frame)
    actions = action_list([{"action": "BUY", "instrument": "X", "amount": "100", "reason": "test"}])

    assert "ma20" in enriched.columns
    assert signal["signal"] in {"TREND_UP", "PULLBACK_BUY_ZONE", "COOLDOWN", "RISK_OFF", "NEUTRAL", "WAIT"}
    assert not curve.empty
    assert "strategy_return_pct" in metrics
    assert len(actions) == 1
