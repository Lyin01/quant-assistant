from quant_assistant.data_provider import AutoProvider, EastMoneyProvider, Quote, TencentProvider


class FakeResponse:
    def __init__(self, body: str, encoding: str = "utf-8") -> None:
        self.body = body
        self.encoding = encoding

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body.encode(self.encoding)


def test_tencent_provider_parses_quote(monkeypatch):
    body = 'v_s_sh512480="1~Semi ETF~512480~2.035~-0.008~-0.39~13675723~279056~~198.07~ETF~";'
    monkeypatch.setattr(
        "quant_assistant.data_provider.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(body, "gbk"),
    )

    quotes, messages = TencentProvider().get_quotes_with_status(["1.512480"])

    quote = quotes["1.512480"]
    assert quote.name == "Semi ETF"
    assert quote.price == 2.035
    assert quote.pct == -0.39
    assert "Tencent: loaded 1 quotes." in messages


def test_eastmoney_provider_treats_malformed_payload_as_empty(monkeypatch):
    monkeypatch.setattr(
        "quant_assistant.data_provider.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse('{"data":[]}'),
    )

    quotes, messages = EastMoneyProvider().get_quotes_with_status(["1.512480"])

    assert quotes == {}
    assert "EastMoney: response contained no quote rows." in messages


def test_eastmoney_provider_skips_non_dict_rows(monkeypatch):
    body = '{"data":{"diff":["bad",{"f12":"512480","f14":"Semi","f2":"2.03","f3":"-0.4","f4":"-0.01","f124":0}]}}'
    monkeypatch.setattr(
        "quant_assistant.data_provider.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(body),
    )

    quotes, messages = EastMoneyProvider().get_quotes_with_status(["1.512480"])

    assert quotes["1.512480"].price == 2.03
    assert "EastMoney: loaded 1 quotes." in messages


def test_auto_provider_skips_akshare_by_default(monkeypatch):
    monkeypatch.delenv("QA_ENABLE_AKSHARE_QUOTES", raising=False)
    monkeypatch.setattr("quant_assistant.data_provider.record_request", lambda *args, **kwargs: None)
    provider = AutoProvider()

    provider.eastmoney.get_quotes_with_status = lambda secids: ({}, ["EastMoney empty"])
    provider.tencent.get_quotes_with_status = lambda secids: (
        {
            "1.512480": Quote(
                secid="1.512480",
                code="512480",
                name="Semi ETF",
                price=2.035,
                pct=-0.39,
                change=-0.008,
                time_text="2026-06-07 10:00:00",
            )
        },
        ["Tencent ok"],
    )

    quotes, messages = provider.get_quotes_with_status(["1.512480"])

    assert provider.akshare is None
    assert quotes["1.512480"].price == 2.035
    assert any("AkShare quotes disabled" in message for message in messages)


def test_auto_provider_ignores_malformed_provider_result(monkeypatch):
    monkeypatch.delenv("QA_ENABLE_AKSHARE_QUOTES", raising=False)
    monkeypatch.setattr("quant_assistant.data_provider.record_request", lambda *args, **kwargs: None)
    provider = AutoProvider()

    provider.eastmoney.get_quotes_with_status = lambda secids: (None, "bad-message")
    provider.tencent.get_quotes_with_status = lambda secids: (
        {
            "1.512480": Quote(
                secid="1.512480",
                code="512480",
                name="Semi ETF",
                price=2.035,
                pct=-0.39,
                change=-0.008,
                time_text="2026-06-07 10:00:00",
            )
        },
        ["Tencent ok"],
    )

    quotes, messages = provider.get_quotes_with_status(["1.512480"])

    assert quotes["1.512480"].price == 2.035
    assert "eastmoney: malformed provider result ignored." in messages
    assert "Tencent ok" in messages


def test_build_provider_uses_default_timeout_for_bad_config_value():
    from quant_assistant.data_provider import build_provider

    provider = build_provider({"market_provider": {"name": "eastmoney", "timeout_seconds": "bad"}})

    assert isinstance(provider, EastMoneyProvider)
    assert provider.timeout == 8


def test_build_provider_uses_auto_when_market_provider_is_not_a_mapping():
    from quant_assistant.data_provider import build_provider

    provider = build_provider({"market_provider": "eastmoney"})

    assert isinstance(provider, AutoProvider)


def test_collect_secids_ignores_bad_quotes_config_shape():
    from quant_assistant.data_provider import collect_secids

    portfolio = {"accounts": {"stock": {"positions": [{"market_proxy": "Semi"}]}}}

    assert collect_secids({"quotes": "bad"}, portfolio) == []
    assert collect_secids({"quotes": {"market": ["1.000001"], "proxies": ["1.512480"]}}, portfolio) == []


def test_collect_secids_ignores_bad_portfolio_account_shape():
    from quant_assistant.data_provider import collect_secids

    config = {"quotes": {"market": {"Index": "1.000001"}, "proxies": {"Semi": "1.512480"}}}
    portfolio = {"accounts": {"bad": "not an account", "stock": {"positions": "bad"}}}

    assert collect_secids(config, portfolio) == ["1.000001", "1.512480"]


def test_quote_for_proxy_ignores_bad_quotes_config_shape():
    from quant_assistant.data_provider import quote_for_proxy

    quote = Quote(
        secid="1.512480",
        code="512480",
        name="Semi ETF",
        price=2.035,
        pct=-0.39,
        change=-0.008,
        time_text="2026-06-07 10:00:00",
    )

    assert quote_for_proxy("Semi", {"quotes": "bad"}, {"1.512480": quote}) is None
    assert quote_for_proxy("Semi", {"quotes": {"proxies": ["1.512480"]}}, {"1.512480": quote}) is None


def test_quote_status_uses_defaults_for_bad_market_provider_shape():
    from quant_assistant.data_provider import quote_status

    status = quote_status({"market_provider": "bad"})

    assert "auto" in status
