from quant_assistant.config import load_json
from quant_assistant.strategy import generate_recommendations
from quant_assistant.analytics import (
    action_list,
    add_advanced_indicators,
    add_indicators,
    backtest_ma_trend,
    interpret_backtest,
    latest_signal,
)
from quant_assistant.importer import parse_ocr_positions, parse_ocr_summary
import pandas as pd


def test_strategy_generates_core_actions():
    config = load_json("config.json")
    portfolio = load_json("portfolio.json")

    recs = generate_recommendations(config, portfolio, quotes={})
    text = "\n".join(f"{rec['action']} {rec['instrument']} {rec['amount']}" for rec in recs)

    assert "易方达中证500" in text
    assert "天弘中证电网设备" in text
    assert "广发中证军工ETF联接" in text


def test_strategy_uses_live_quotes_when_enabled():
    from quant_assistant.data_provider import Quote

    config = load_json("config.json")
    config["market_provider"]["use_live_proxy_for_decisions"] = True
    portfolio = load_json("portfolio.json")

    # Empty quotes => fallback to last_daily_pct
    recs_fallback = generate_recommendations(config, portfolio, quotes={})

    # Simulate a big up-day quote for the AI proxy
    proxies = config["quotes"]["proxies"]
    ai_secid = proxies["人工智能"]
    quotes = {
        ai_secid: Quote(secid=ai_secid, code="515070", name="人工智能ETF", price=1.5, pct=3.0, change=0.04, time_text="2025-01-01 15:00:00"),
    }
    recs_live = generate_recommendations(config, portfolio, quotes=quotes)

    text_fallback = "\n".join(r["reason"] for r in recs_fallback)
    text_live = "\n".join(r["reason"] for r in recs_live)

    # With a 3% up quote, the live recs should reference the live pct value
    assert "3.00" in text_live or "涨幅" in text_live
    # The two sets should differ because live quotes change the decision inputs
    assert text_fallback != text_live


def test_stock_rules_use_live_quote_price():
    from quant_assistant.data_provider import Quote

    config = load_json("config.json")
    config["market_provider"]["use_live_proxy_for_decisions"] = True
    portfolio = load_json("portfolio.json")
    semi_secid = config["quotes"]["proxies"]["半导体"]

    quotes = {
        semi_secid: Quote(
            secid=semi_secid,
            code="512480",
            name="半导体ETF",
            price=1.990,
            pct=-1.2,
            change=-0.02,
            time_text="2026-05-15 10:30:00",
        )
    }

    recs = generate_recommendations(config, portfolio, quotes=quotes)
    text = "\n".join(f"{rec['action']} {rec['instrument']} {rec['reason']}" for rec in recs)

    assert "BUY 半导体" in text
    assert "1.990" in text


def test_use_live_proxy_default_is_true():
    config = load_json("config.json")
    assert config["market_provider"]["use_live_proxy_for_decisions"] is True


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
    assert signal["signal"] in {"趋势向上", "低吸观察", "冷却等待", "防守观望", "信号中性", "等待数据"}
    assert not curve.empty
    assert "策略收益" in metrics
    assert len(actions) == 1


def test_interpret_backtest_warns_when_strategy_loses_to_buy_hold():
    interpretation = interpret_backtest(
        {
            "策略收益": -5.34,
            "持有收益": 36.86,
            "最大回撤": -11.31,
            "交易次数": 53.0,
            "天数": 600.0,
        }
    )

    assert interpretation["结论"] == "跑输持有"
    assert "不建议用于实盘参考" in interpretation["建议"]


def test_parse_ocr_positions():
    frame = parse_ocr_positions(
        """
        半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%
        机器人 | 349.20 | 300 | 300 | 1.164 | 1.031 | +39.90 | +12.90%
        """
    )

    assert list(frame["name"]) == ["半导体", "机器人"]
    assert list(frame["tag"]) == ["semiconductor", "robot"]
    assert frame.loc[0, "market_value"] == 203.50
    assert frame.loc[0, "shares"] == 100
    assert frame.loc[0, "price"] == 2.035
    assert frame.loc[0, "cost"] == 2.071
    assert frame.loc[0, "holding_pnl"] == -3.60
    assert frame.loc[1, "holding_pnl_pct"] == 12.90


def test_add_advanced_indicators():
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

    enriched = add_advanced_indicators(frame)

    # MACD columns
    assert "macd" in enriched.columns
    assert "macd_signal" in enriched.columns
    assert "macd_hist" in enriched.columns

    # RSI
    assert "rsi14" in enriched.columns

    # Bollinger Bands
    assert "bb_middle" in enriched.columns
    assert "bb_upper" in enriched.columns
    assert "bb_lower" in enriched.columns


def test_add_advanced_indicators_empty_frame():
    empty = pd.DataFrame()
    result = add_advanced_indicators(empty)
    assert result.empty


def test_add_advanced_indicators_short_frame():
    short = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10),
            "close": range(10),
        }
    )
    result = add_advanced_indicators(short)
    # Should return unchanged since < 26 rows
    assert "macd" not in result.columns


def test_add_advanced_indicators_combined_with_basic():
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
    enriched = add_advanced_indicators(enriched)

    # Both basic and advanced indicators present
    assert "ma20" in enriched.columns
    assert "ma60" in enriched.columns
    assert "macd" in enriched.columns
    assert "rsi14" in enriched.columns
    assert "bb_upper" in enriched.columns


def test_parse_fund_ocr_format_and_summary():
    text = """
    账户资产: 18118.73
    场内穿透: -228.25
    易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%
    天弘中证电网设备 | 3270.40 | -3.24% | +363.23 | +12.49%
    """
    summary = parse_ocr_summary(text)
    frame = parse_ocr_positions(text)

    assert summary["total_assets"] == 18118.73
    assert summary["today_pnl"] == -228.25
    assert list(frame["name"]) == ["易方达中证500", "天弘中证电网设备"]
    assert frame.loc[0, "last_daily_pct"] == -1.54
    assert frame.loc[0, "holding_pnl"] == -76.65
    assert frame.loc[1, "holding_pnl_pct"] == 12.49
