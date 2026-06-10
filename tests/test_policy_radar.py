import pandas as pd

from quant_assistant import policy_radar


def test_parse_eastmoney_payload_accepts_jsonp_wrapper():
    raw = 'var ajaxResult={"LivesList":[{"title":"AI policy","showtime":"2026-06-10"}]};'

    payload = policy_radar._parse_eastmoney_payload(raw)

    assert payload["LivesList"][0]["title"] == "AI policy"


def test_parse_eastmoney_payload_returns_empty_for_bad_response():
    assert policy_radar._parse_eastmoney_payload("not json") == {}
    assert policy_radar._parse_eastmoney_payload("callback({bad json});") == {}


def test_normalize_policy_frame_skips_bad_rows_and_adds_columns():
    frame = policy_radar._normalize_policy_frame(
        [
            "bad-row",
            {"title": ""},
            {"title": "AI policy", "tags": "AI", "is_policy": True},
        ]
    )

    assert list(frame.columns) == ["title", "time", "source", "url", "tags", "is_policy"]
    assert frame.to_dict(orient="records") == [
        {"title": "AI policy", "time": "", "source": "", "url": "", "tags": "AI", "is_policy": True}
    ]


def test_fetch_policy_news_ignores_malformed_cache(monkeypatch):
    monkeypatch.setattr(policy_radar, "load_generic_cache", lambda key: {"bad": "cache"})
    monkeypatch.setattr(policy_radar, "_fetch_eastmoney_news", lambda limit: [])

    frame, messages = policy_radar.fetch_policy_news(limit=5)

    assert frame.empty
    assert "EastMoney news: 0 items" in messages


def test_summarize_policy_trends_tolerates_missing_columns():
    assert policy_radar.summarize_policy_trends(pd.DataFrame([{"title": "AI"}])) == []
