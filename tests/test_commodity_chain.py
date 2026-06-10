from quant_assistant import commodity_chain


def test_akshare_spot_fetch_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(commodity_chain.AKSHARE_SPOT_ENABLED_ENV, raising=False)

    price, message = commodity_chain._fetch_akshare_spot("any")

    assert price is None
    assert "AkShare spot disabled" in message


def test_chain_fetch_keeps_futures_when_spot_is_disabled(monkeypatch):
    monkeypatch.delenv(commodity_chain.AKSHARE_SPOT_ENABLED_ENV, raising=False)
    monkeypatch.setattr(commodity_chain, "load_generic_cache", lambda _key: None)
    monkeypatch.setattr(commodity_chain, "save_generic_cache", lambda _key, _value: None)
    monkeypatch.setitem(
        commodity_chain.CHAINS,
        "test-chain",
        {
            "description": "test",
            "links": [
                {"name": "future-link", "source": "futures", "code": "FU", "unit": "u"},
                {"name": "spot-link", "source": "spot", "code": "SP", "unit": "u"},
            ],
        },
    )
    monkeypatch.setattr(commodity_chain, "_fetch_futures_price", lambda _code: (12.3, "future ok"))

    prices, messages = commodity_chain.fetch_chain_prices("test-chain")

    assert len(prices) == 1
    assert 12.3 in prices[0].values()
    assert "future ok" in messages
    assert any("AkShare spot disabled" in message for message in messages)


def test_chain_fetch_skips_malformed_links(monkeypatch):
    monkeypatch.setattr(commodity_chain, "load_generic_cache", lambda _key: None)
    monkeypatch.setattr(commodity_chain, "save_generic_cache", lambda _key, _value: None)
    monkeypatch.setitem(
        commodity_chain.CHAINS,
        "bad-link-chain",
        {
            "description": "test",
            "links": [
                {"name": "missing-code", "source": "futures", "unit": "u"},
                "not-a-link",
                {"name": "future-link", "source": "futures", "code": "FU", "unit": "u"},
            ],
        },
    )
    monkeypatch.setattr(commodity_chain, "_fetch_futures_price", lambda _code: (12.3, "future ok"))

    prices, messages = commodity_chain.fetch_chain_prices("bad-link-chain")

    assert len(prices) == 1
    assert prices[0]["环节"] == "future-link"
    assert any("skipped malformed link" in message for message in messages)


def test_chain_summary_skips_malformed_links(monkeypatch):
    monkeypatch.setitem(
        commodity_chain.CHAINS,
        "summary-bad-link-chain",
        {
            "description": "test",
            "links": [
                {"name": "missing-code", "source": "futures", "unit": "u"},
                "not-a-link",
                {"name": "future-link", "source": "futures", "code": "FU", "unit": "u"},
            ],
        },
    )

    summary = commodity_chain.chain_summary("summary-bad-link-chain")

    assert summary == {
        "name": "summary-bad-link-chain",
        "description": "test",
        "links": ["future-link"],
    }
