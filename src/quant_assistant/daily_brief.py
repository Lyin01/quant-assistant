from __future__ import annotations

from datetime import date, datetime, timedelta


def assess_quote_freshness(time_texts: list[str], today: date | None = None) -> dict[str, object]:
    current_day = today or date.today()
    latest = _latest_datetime(time_texts)
    if latest is None:
        return {
            "reliable": False,
            "status": "无实时行情",
            "detail": "未获取到可用行情时间，建议只参考持仓快照和历史复盘。",
        }

    latest_day = latest.date()
    if latest_day == current_day:
        return {
            "reliable": True,
            "status": "数据为今日行情",
            "detail": f"数据截止 {latest.strftime('%Y-%m-%d %H:%M:%S')}。",
        }

    if current_day.weekday() >= 5 and latest_day >= _previous_friday(current_day):
        return {
            "reliable": True,
            "status": "非交易日沿用上一交易日数据",
            "detail": f"今天是非交易日，数据截止 {latest.strftime('%Y-%m-%d %H:%M:%S')}。",
        }

    return {
        "reliable": False,
        "status": "行情数据可能过期",
        "detail": f"最新行情时间为 {latest.strftime('%Y-%m-%d %H:%M:%S')}，请刷新或检查数据源后再决策。",
    }


def friendly_source_messages(messages: list[str]) -> list[str]:
    friendly: list[str] = []
    for message in messages:
        if "RemoteDisconnected" in message or "Connection aborted" in message:
            friendly.append("主数据源连接中断：远端未返回完整响应。")
            continue
        if "alternate" in message.lower() and "history" in message.lower():
            friendly.append(_rows_message(message, "已使用备用数据"))
            continue
        if "fallback" in message.lower():
            friendly.append(_rows_message(message, "已使用备用数据源"))
            continue
        if "Cache hit" in message or "cache hit" in message:
            friendly.append("命中本地缓存。")
            continue
        friendly.append(message)
    return friendly


def build_daily_cockpit(
    data_reliable: bool,
    data_detail: str,
    actionable_count: int,
    watchlist_count: int,
    coverage_issue_count: int,
) -> list[dict[str, str]]:
    data_judgement = "数据可用于复盘和条件检查。" if data_reliable else "暂不建议依据实时行情决策。"
    holding_judgement = (
        "暂无明显策略覆盖缺口。"
        if coverage_issue_count == 0
        else f"发现 {coverage_issue_count} 个持仓覆盖缺口，需要先补策略标签或行情代理。"
    )
    opportunity_judgement = (
        f"有 {actionable_count} 条行动清单，需人工复核。"
        if actionable_count
        else f"暂无行动清单，有 {watchlist_count} 条观察项。"
    )
    return [
        {
            "问题": "今天数据可靠吗？",
            "判断": data_judgement,
            "依据": data_detail,
            "下一步": "数据异常时先刷新数据源，不做新增决策。",
        },
        {
            "问题": "我的持仓有没有风险？",
            "判断": holding_judgement,
            "依据": "策略覆盖检查用于发现导入持仓未纳入规则的问题。",
            "下一步": "先修正覆盖缺口，再看买卖建议。",
        },
        {
            "问题": "今天有没有值得人工复核的机会？",
            "判断": opportunity_judgement,
            "依据": "只做条件触发和观察清单，不预测未来涨跌。",
            "下一步": "逐条检查原因、仓位和数据时间后再决定是否操作。",
        },
    ]


def _latest_datetime(time_texts: list[str]) -> datetime | None:
    parsed: list[datetime] = []
    for text in time_texts:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                parsed.append(datetime.strptime(str(text), fmt))
                break
            except ValueError:
                continue
    if not parsed:
        return None
    return max(parsed)


def _previous_friday(day: date) -> date:
    days_since_friday = (day.weekday() - 4) % 7
    return day - timedelta(days=days_since_friday)


def _rows_message(message: str, prefix: str) -> str:
    marker = " rows"
    if marker not in message:
        return f"{prefix}。"
    before = message.split(marker, 1)[0]
    row_count = before.rsplit(",", 1)[-1].strip()
    if row_count.isdigit():
        return f"{prefix}，样本 {row_count} 行。"
    return f"{prefix}。"
