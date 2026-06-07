from datetime import date

import pandas as pd

from quant_assistant import market_data


def test_fetch_history_uses_tencent_before_disabled_akshare(monkeypatch):
    monkeypatch.delenv(market_data.AKSHARE_MARKET_DATA_ENABLED_ENV, raising=False)
    monkeypatch.setattr(market_data, "load_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr(market_data, "save_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr(market_data, "_fetch_eastmoney_history", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        market_data,
        "_fetch_tencent_history",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "close": [1.0, 1.1],
            }
        ),
    )

    frame, messages = market_data.fetch_history("1.512480", date(2026, 1, 1), date(2026, 1, 2))

    assert len(frame) == 2
    assert any("Tencent history fallback" in message for message in messages)
    assert not any("AkShare" in message for message in messages)


def test_fetch_etf_ranking_skips_akshare_by_default(monkeypatch):
    monkeypatch.delenv(market_data.AKSHARE_MARKET_DATA_ENABLED_ENV, raising=False)
    monkeypatch.setattr(market_data, "_fetch_eastmoney_etf_ranking", lambda limit: pd.DataFrame())
    monkeypatch.setattr(
        market_data,
        "FALLBACK_ETF_UNIVERSE",
        [("159915", "创业板ETF"), ("512480", "半导体ETF")],
    )

    def fake_fetch_history(secid, start, end, adjust):
        if secid == "0.159915":
            close = [1.0, 1.1]
        else:
            close = [1.0, 0.95]
        return (
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                    "close": close,
                    "volume": [100, 120],
                }
            ),
            ["history ok"],
        )

    monkeypatch.setattr(market_data, "fetch_history", fake_fetch_history)

    frame, messages = market_data.fetch_etf_ranking(5)

    assert list(frame["code"]) == ["159915", "512480"]
    assert frame.loc[0, "pct"] == 10.000000000000009
    assert frame.loc[1, "pct"] == -5.000000000000004
    assert any("AkShare market data disabled" in message for message in messages)
    assert any("Fallback ETF universe ranking" in message for message in messages)


def test_fallback_etf_snapshot_keeps_row_when_history_missing(monkeypatch):
    monkeypatch.setattr(
        market_data,
        "fetch_history",
        lambda secid, start, end, adjust: (pd.DataFrame(), ["empty"]),
    )
    monkeypatch.setattr(market_data, "FALLBACK_ETF_UNIVERSE", [("159915", "创业板ETF")])

    row = market_data._fallback_etf_snapshot("159915", "创业板ETF", 0)

    assert row["code"] == "159915"
    assert row["name"] == "创业板ETF"
    assert row["price"] is None
    assert row["pct"] is None


def test_fallback_etf_snapshot_keeps_row_when_history_raises(monkeypatch):
    def raise_history(secid, start, end, adjust):
        raise TimeoutError("history timeout")

    monkeypatch.setattr(market_data, "fetch_history", raise_history)
    monkeypatch.setattr(market_data, "FALLBACK_ETF_UNIVERSE", [("159915", "创业板ETF")])

    row = market_data._fallback_etf_snapshot("159915", "创业板ETF", 0)

    assert row["code"] == "159915"
    assert row["name"] == "创业板ETF"
    assert row["price"] is None
    assert row["pct"] is None
