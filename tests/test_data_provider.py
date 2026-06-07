from quant_assistant.data_provider import AutoProvider, Quote, TencentProvider


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return 'v_s_sh512480="1~半导体ETF国联安~512480~2.035~-0.008~-0.39~13675723~279056~~198.07~ETF~";'.encode(
            "gbk"
        )


def test_tencent_provider_parses_quote(monkeypatch):
    monkeypatch.setattr("quant_assistant.data_provider.urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    quotes, messages = TencentProvider().get_quotes_with_status(["1.512480"])

    quote = quotes["1.512480"]
    assert quote.name == "半导体ETF国联安"
    assert quote.price == 2.035
    assert quote.pct == -0.39
    assert "Tencent: loaded 1 quotes." in messages


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
