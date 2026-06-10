from quant_assistant.data_provider import TencentProvider


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
