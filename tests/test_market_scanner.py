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


def test_fetch_all_etfs_uses_cached_list_before_network(monkeypatch):
    cached_rows = [
        {"code": "159915", "name": "创业板ETF", "price": "2.0", "amount": "100"},
    ]

    monkeypatch.setattr(
        market_scanner,
        "load_generic_cache",
        lambda key: cached_rows if key == market_scanner.ETF_LIST_CACHE_KEY else None,
    )

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be used when ETF list cache is warm")

    monkeypatch.setattr(market_scanner.urllib.request, "urlopen", fail_network)

    frame = market_scanner.fetch_all_etfs()

    assert frame.loc[0, "code"] == "159915"
    assert frame.loc[0, "name"] == "创业板ETF"
    assert frame.loc[0, "price"] == 2.0


def test_fetch_all_etfs_skips_akshare_list_by_default(monkeypatch):
    monkeypatch.delenv(market_scanner.AKSHARE_ETF_LIST_ENABLED_ENV, raising=False)
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: None)

    def fail_eastmoney(*args, **kwargs):
        raise TimeoutError("eastmoney timeout")

    monkeypatch.setattr(market_scanner.urllib.request, "urlopen", fail_eastmoney)

    frame = market_scanner.fetch_all_etfs()

    assert frame.empty
    assert list(frame.columns) == market_scanner.ETF_LIST_COLUMNS


def test_scan_etfs_uses_fallback_universe_when_etf_list_is_empty(monkeypatch):
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: None)
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda key, value: None)
    monkeypatch.setattr(market_scanner, "fetch_all_etfs", lambda: pd.DataFrame())
    monkeypatch.setattr(
        market_scanner,
        "_fallback_etf_universe",
        lambda: pd.DataFrame([{"code": "159915", "name": "创业板ETF", "price": None, "amount": 1}]),
    )
    monkeypatch.setattr(
        market_scanner,
        "_scan_one",
        lambda code, name, price, force_refresh=False: {
            "code": code,
            "name": name,
            "price": 2.0,
            "score": 72.5,
        },
    )

    frame, messages = market_scanner.scan_etfs(top_n=1, max_workers=1)

    assert frame.loc[0, "名称"] == "创业板ETF"
    assert any("fallback universe" in message for message in messages)


def test_scan_etfs_handles_missing_amount_column(monkeypatch):
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: None)
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda key, value: None)
    monkeypatch.setattr(
        market_scanner,
        "fetch_all_etfs",
        lambda: pd.DataFrame([{"code": "159915", "name": "创业板ETF", "price": 2.0}]),
    )
    monkeypatch.setattr(
        market_scanner,
        "_scan_one",
        lambda code, name, price, force_refresh=False: {
            "code": code,
            "name": name,
            "price": price,
            "score": 72.5,
        },
    )

    frame, messages = market_scanner.scan_etfs(top_n=1, max_workers=1)

    assert frame.loc[0, "名称"] == "创业板ETF"
    assert any("missing turnover amount" in message for message in messages)


def test_scan_one_uses_latest_close_when_list_price_is_missing(monkeypatch):
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: None)
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda key, value: None)
    monkeypatch.setattr(
        market_scanner,
        "_fetch_tencent_klines",
        lambda code, days=120: pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=20),
                "close": [1.0] * 19 + [2.0],
            }
        ),
    )
    monkeypatch.setattr(market_scanner, "compute_factors", lambda klines: {"ret_5": 1.0})
    monkeypatch.setattr(market_scanner, "_score", lambda factors, current_price: current_price)

    result = market_scanner._scan_one("159915", "创业板ETF", None, force_refresh=True)

    assert result is not None
    assert result["price"] == 2.0
    assert result["score"] == 2.0


def test_scan_one_ignores_malformed_item_cache(monkeypatch):
    saved = {}
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: ["bad-cache"])
    monkeypatch.setattr(market_scanner, "save_generic_cache", lambda key, value: saved.update({key: value}))
    monkeypatch.setattr(
        market_scanner,
        "_fetch_tencent_klines",
        lambda code, days=120: pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=20),
                "close": [1.0] * 20,
                "volume": [100] * 20,
            }
        ),
    )
    monkeypatch.setattr(market_scanner, "compute_factors", lambda klines: {"ret_5": 1.0})
    monkeypatch.setattr(market_scanner, "_score", lambda factors, current_price: 66.0)

    result = market_scanner._scan_one("159915", "创业板ETF", 2.0)

    assert result is not None
    assert result["score"] == 66.0
    assert result["from_cache"] is False
    assert saved["scanner_159915"]["score"] == 66.0
