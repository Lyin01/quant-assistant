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
