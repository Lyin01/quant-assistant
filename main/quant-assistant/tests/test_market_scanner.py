import pandas as pd

from quant_assistant import market_scanner


def test_scan_etfs_uses_summary_cache_before_fetching_list(monkeypatch):
    cached_rows = [
        {"排名": 1, "代码": "159915", "名称": "创业板ETF", "综合评分": 72.5},
    ]

    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: cached_rows if key.startswith("scanner_summary") else None)

    def fail_fetch():
        raise AssertionError("ETF list should not be fetched when summary cache is warm")

    monkeypatch.setattr(market_scanner, "fetch_all_etfs", fail_fetch)

    frame, messages = market_scanner.scan_etfs()

    assert isinstance(frame, pd.DataFrame)
    assert frame.loc[0, "名称"] == "创业板ETF"
    assert "cache hit" in messages[0].lower()


def test_default_scan_limit_is_small_enough_for_interactive_use():
    assert market_scanner.DEFAULT_SCAN_LIMIT == 30


def test_compute_factors_scores_continuation_trend():
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    closes = [1 + i * 0.01 for i in range(70)] + [1.70, 1.72, 1.74, 1.76, 1.78, 1.77, 1.79, 1.81, 1.83, 1.85]
    frame = pd.DataFrame(
        {
            "date": dates,
            "close": closes,
            "volume": [1000 + i * 5 for i in range(80)],
        }
    )

    factors = market_scanner.compute_factors(frame)

    assert factors["trend_score"] == 4
    assert factors["up_days_5"] >= 4
    assert factors["up_days_10"] >= 8
    assert factors["ma20_slope_5"] > 0
    assert factors["continuation_score"] >= 65
    assert market_scanner.trend_grade(factors["continuation_score"]) in {"趋势向上", "强趋势"}


def test_scan_etfs_ranks_by_continuation_score(monkeypatch):
    etfs = pd.DataFrame(
        [
            {"code": "510500", "name": "中证500ETF", "price": 6.0, "amount": 100},
            {"code": "159915", "name": "创业板ETF", "price": 2.0, "amount": 90},
        ]
    )
    rows = {
        "510500": {
            "code": "510500",
            "name": "中证500ETF",
            "price": 6.0,
            "score": 70,
            "candidate_score": 55,
            "continuation_score": 55,
            "trend_grade": "观察",
            "action_note": "有转强迹象，等量价继续确认",
        },
        "159915": {
            "code": "159915",
            "name": "创业板ETF",
            "price": 2.0,
            "score": 60,
            "candidate_score": 82,
            "continuation_score": 82,
            "trend_grade": "强趋势",
            "action_note": "强势但接近高位，不追高，等回踩",
        },
    }

    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda _key: None)
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda _key, _value: None)
    monkeypatch.setattr(market_scanner, "fetch_all_etfs", lambda: etfs)
    monkeypatch.setattr(
        market_scanner,
        "_scan_one",
        lambda code, name, price, force_refresh=False, asset_type="ETF", amount=0.0, mode="balanced": rows[code],
    )

    frame, _messages = market_scanner.scan_etfs(top_n=2, max_workers=1)

    assert frame.loc[0, "代码"] == "159915"
    assert frame.loc[0, "连涨趋势分"] == 82
    assert frame.loc[0, "趋势等级"] == "强趋势"


def test_scan_market_can_scan_a_shares(monkeypatch):
    stocks = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台", "price": 1500.0, "amount": 200, "asset_type": "A股"},
        ]
    )

    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda _key: None)
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda _key, _value: None)
    monkeypatch.setattr(market_scanner, "fetch_scan_universe", lambda universe, include_defensive=False: stocks)
    monkeypatch.setattr(
        market_scanner,
        "_scan_one",
        lambda code, name, price, force_refresh=False, asset_type="ETF", amount=0.0, mode="balanced": {
            "code": code,
            "name": name,
            "asset_type": asset_type,
            "price": price,
            "score": 75,
            "candidate_score": 70,
            "continuation_score": 70,
            "trend_grade": "趋势向上",
            "trade_suggestion": "小仓试探",
            "sell_suggestion": "已有仓位：继续持有",
            "action_note": "趋势较顺，适合加入观察清单",
        },
    )

    frame, messages = market_scanner.scan_market(universe="stock", top_n=1, max_workers=1)

    assert frame.loc[0, "类型"] == "A股"
    assert frame.loc[0, "代码"] == "600519"
    assert "A股" in messages[0]


def test_filter_scan_universe_excludes_defensive_etfs_by_default():
    frame = pd.DataFrame(
        [
            {"code": "511880", "name": "银华日利ETF", "price": 100, "amount": 10, "asset_type": "ETF"},
            {"code": "588000", "name": "科创50ETF华夏", "price": 2, "amount": 9, "asset_type": "ETF"},
            {"code": "600000", "name": "浦发银行", "price": 8, "amount": 8, "asset_type": "A股"},
            {"code": "600001", "name": "ST测试", "price": 1, "amount": 7, "asset_type": "A股"},
        ]
    )

    filtered = market_scanner._filter_scan_universe(frame)

    assert set(filtered["code"]) == {"588000", "600000"}


def test_candidate_score_penalizes_overheated_high_position():
    factors = {
        "continuation_score": 90,
        "rsi": 86,
        "drawdown_20": -0.2,
        "ret_5": 10,
        "ret_20": 45,
        "volatility": 8,
        "consecutive_up_days": 5,
        "volume_confirm": 0,
        "macd_hist": 1,
        "up_days_10": 7,
    }

    balanced = market_scanner._candidate_score(factors, amount=500_000_000, asset_type="A股", mode="balanced")
    aggressive = market_scanner._candidate_score(factors, amount=500_000_000, asset_type="A股", mode="aggressive")

    assert balanced < factors["continuation_score"]
    assert aggressive >= balanced
    assert "RSI过热" in market_scanner.risk_note(factors, 500_000_000, "A股")


def test_trade_suggestion_waits_after_fast_high_run():
    factors = {
        "candidate_score": 88,
        "continuation_score": 92,
        "trend_score": 4,
        "drawdown_20": 0,
        "rsi": 78,
        "ret_5": 9,
        "ret_20": 20,
        "volume_confirm": 1,
    }

    assert market_scanner.trade_suggestion(factors, "A股").startswith("等回踩")


def test_trade_suggestion_allows_small_probe_on_pullback():
    factors = {
        "candidate_score": 76,
        "continuation_score": 78,
        "trend_score": 4,
        "drawdown_20": -3,
        "rsi": 62,
        "ret_5": 2,
        "ret_20": 8,
        "volume_confirm": 1,
    }

    assert "小仓试探" in market_scanner.trade_suggestion(factors, "A股")
