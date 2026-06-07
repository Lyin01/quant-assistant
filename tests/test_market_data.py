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

    frame, messages = market_data.fetch_etf_ranking(5)

    assert frame.empty
    assert any("AkShare market data disabled" in message for message in messages)
