from quant_assistant import macro_dashboard


def test_fetch_macro_indicators_skips_akshare_by_default(monkeypatch):
    monkeypatch.delenv(macro_dashboard.AKSHARE_MACRO_ENABLED_ENV, raising=False)
    monkeypatch.setattr(macro_dashboard, "load_generic_cache", lambda key: None)

    data, messages = macro_dashboard.fetch_macro_indicators()

    assert data == {}
    assert any("AkShare macro disabled" in message for message in messages)


def test_fetch_macro_indicators_uses_cache_when_akshare_disabled(monkeypatch):
    monkeypatch.delenv(macro_dashboard.AKSHARE_MACRO_ENABLED_ENV, raising=False)
    monkeypatch.setattr(macro_dashboard, "load_generic_cache", lambda key: {"cn_10y_bond": 1.7})

    data, messages = macro_dashboard.fetch_macro_indicators()

    assert data == {"cn_10y_bond": 1.7}
    assert messages == ["Macro: cache hit"]
