from datetime import date

from quant_assistant.daily_brief import (
    assess_quote_freshness,
    build_daily_cockpit,
    friendly_source_messages,
)


def test_quote_freshness_accepts_previous_friday_on_weekend():
    freshness = assess_quote_freshness(["2026-05-15 16:12:00"], today=date(2026, 5, 17))

    assert freshness["reliable"] is True
    assert "非交易日" in freshness["status"]
    assert "2026-05-15" in freshness["detail"]


def test_quote_freshness_flags_stale_trading_day_data():
    freshness = assess_quote_freshness(["2026-05-15 16:12:00"], today=date(2026, 5, 18))

    assert freshness["reliable"] is False
    assert "过期" in freshness["status"]


def test_friendly_source_messages_hide_raw_connection_trace():
    messages = friendly_source_messages(
        [
            "AkShare index history failed for sz399001: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))",
            "AkShare alternate index history: sz399001, 355 rows.",
        ]
    )

    joined = "\n".join(messages)
    assert "RemoteDisconnected" not in joined
    assert "主数据源连接中断" in joined
    assert "备用数据" in joined


def test_daily_cockpit_centers_the_three_user_questions():
    rows = build_daily_cockpit(
        data_reliable=False,
        data_detail="实时行情不可用",
        actionable_count=0,
        watchlist_count=3,
        coverage_issue_count=2,
    )

    assert [row["问题"] for row in rows] == [
        "今天数据可靠吗？",
        "我的持仓有没有风险？",
        "今天有没有值得人工复核的机会？",
    ]
    assert "暂不建议" in rows[0]["判断"]
    assert "2" in rows[1]["判断"]
    assert "3" in rows[2]["判断"]
