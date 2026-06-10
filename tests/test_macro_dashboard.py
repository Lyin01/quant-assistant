from quant_assistant import macro_dashboard


def test_fetch_macro_indicators_skips_akshare_by_default(monkeypatch):
    monkeypatch.delenv(macro_dashboard.AKSHARE_MACRO_ENABLED_ENV, raising=False)
    monkeypatch.setattr(macro_dashboard, "load_generic_cache", lambda key: None)
    monkeypatch.setattr(
        macro_dashboard,
        "_fetch_public_macro_fallback",
        lambda: ({"us_10y_bond": 4.25}, ["FRED DGS10: ok"]),
    )
    saved = {}
    monkeypatch.setattr(macro_dashboard, "save_generic_cache", lambda key, data: saved.update({key: data}))

    data, messages = macro_dashboard.fetch_macro_indicators()

    assert data == {"us_10y_bond": 4.25}
    assert any("AkShare macro disabled" in message for message in messages)
    assert "FRED DGS10: ok" in messages
    assert saved == {macro_dashboard.MACRO_CACHE_KEY: {"us_10y_bond": 4.25}}


def test_fetch_macro_indicators_uses_cache_when_akshare_disabled(monkeypatch):
    monkeypatch.delenv(macro_dashboard.AKSHARE_MACRO_ENABLED_ENV, raising=False)
    monkeypatch.setattr(macro_dashboard, "load_generic_cache", lambda key: {"cn_10y_bond": 1.7})

    data, messages = macro_dashboard.fetch_macro_indicators()

    assert data == {"cn_10y_bond": 1.7}
    assert messages == ["Macro: cache hit"]


def test_fetch_macro_indicators_ignores_malformed_cache(monkeypatch):
    monkeypatch.delenv(macro_dashboard.AKSHARE_MACRO_ENABLED_ENV, raising=False)
    monkeypatch.setattr(macro_dashboard, "load_generic_cache", lambda key: ["bad-cache"])
    monkeypatch.setattr(
        macro_dashboard,
        "_fetch_public_macro_fallback",
        lambda: ({"usdcny": 7.18}, ["Yahoo USDCNY=X: ok"]),
    )

    data, messages = macro_dashboard.fetch_macro_indicators()

    assert data == {"usdcny": 7.18}
    assert "Macro: ignored malformed cache" in messages
    assert "Yahoo USDCNY=X: ok" in messages


def test_public_macro_fallback_parses_fred_and_yahoo(monkeypatch):
    def fake_read_url_text(url: str, referer: str) -> str:
        if "%5ETNX" in url:
            return '{"chart":{"result":[{"indicators":{"quote":[{"close":[null,4.12]}]}}]}}'
        if "FEDFUNDS" in url:
            return "observation_date,FEDFUNDS\n2026-01-01,4.33\n"
        if "CPIAUCSL" in url:
            values = [300 + index for index in range(13)]
            rows = ["observation_date,CPIAUCSL"]
            rows.extend(f"2025-{index + 1:02d}-01,{value}" for index, value in enumerate(values))
            return "\n".join(rows)
        if "USDCNY%3DX" in url:
            return '{"chart":{"result":[{"indicators":{"quote":[{"close":[null,7.12,7.18]}]}}]}}'
        raise AssertionError(url)

    monkeypatch.setattr(macro_dashboard, "_read_url_text", fake_read_url_text)

    data, messages = macro_dashboard._fetch_public_macro_fallback()

    assert data["us_10y_bond"] == 4.12
    assert data["fed_rate"] == 4.33
    assert data["us_cpi_yoy"] == 4.0
    assert data["usdcny"] == 7.18
    assert "Yahoo ^TNX: ok" in messages
    assert "Yahoo USDCNY=X: ok" in messages


def test_public_macro_fallback_uses_fred_10y_when_yahoo_tnx_missing(monkeypatch):
    def fake_read_url_text(url: str, referer: str) -> str:
        if "%5ETNX" in url:
            return '{"chart":{"result":[{"indicators":{"quote":[{"close":[null]}]}}]}}'
        if "DGS10" in url:
            return "observation_date,DGS10\n2026-01-01,4.51\n"
        if "FEDFUNDS" in url:
            return "observation_date,FEDFUNDS\n2026-01-01,4.33\n"
        if "CPIAUCSL" in url:
            values = [300 + index for index in range(13)]
            rows = ["observation_date,CPIAUCSL"]
            rows.extend(f"2025-{index + 1:02d}-01,{value}" for index, value in enumerate(values))
            return "\n".join(rows)
        if "USDCNY%3DX" in url:
            return '{"chart":{"result":[{"indicators":{"quote":[{"close":[7.18]}]}}]}}'
        raise AssertionError(url)

    monkeypatch.setattr(macro_dashboard, "_read_url_text", fake_read_url_text)

    data, messages = macro_dashboard._fetch_public_macro_fallback()

    assert data["us_10y_bond"] == 4.51
    assert "Yahoo ^TNX: no numeric data" in messages
    assert "FRED DGS10: ok" in messages
