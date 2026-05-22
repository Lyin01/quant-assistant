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


def test_scan_etfs_handles_empty_etf_list(monkeypatch):
    monkeypatch.setattr(market_scanner, "load_generic_cache", lambda key: None)
    monkeypatch.setattr(market_scanner, "fetch_all_etfs", lambda: pd.DataFrame())

    frame, messages = market_scanner.scan_etfs()

    assert frame.empty
    assert any("empty" in message.lower() for message in messages)


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
