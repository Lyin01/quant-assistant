from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.analytics import action_list, add_indicators, backtest_ma_trend, latest_signal
from quant_assistant.config import load_json
from quant_assistant.data_provider import build_provider, collect_secids, quote_status
from quant_assistant.importer import (
    dataframe_to_positions,
    normalize_import_table,
    parse_ocr_positions,
    read_uploaded_table,
    template_frame,
)
from quant_assistant.market_data import fetch_etf_ranking, fetch_history, instrument_options
from quant_assistant.strategy import generate_recommendations


st.set_page_config(page_title="Quant Assistant", layout="wide")

config = load_json(ROOT / "config.json")
portfolio = load_json(ROOT / "portfolio.json")
fund = portfolio["accounts"]["fund"]
stock = portfolio["accounts"]["stock"]
options = instrument_options(config)


@st.cache_data(ttl=600, show_spinner=False)
def cached_quotes(config_data: dict, portfolio_data: dict):
    provider = build_provider(config_data)
    secids = collect_secids(config_data, portfolio_data)
    return provider.get_quotes_with_status(secids)


@st.cache_data(ttl=900, show_spinner=False)
def cached_history(secid: str, start_text: str, end_text: str, adjust: str) -> tuple[pd.DataFrame, list[str]]:
    return fetch_history(secid, date.fromisoformat(start_text), date.fromisoformat(end_text), adjust)


@st.cache_data(ttl=900, show_spinner=False)
def cached_etf_ranking(limit: int) -> tuple[pd.DataFrame, list[str]]:
    return fetch_etf_ranking(limit)


def _quote_frame(quotes: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "名称": quote.name,
                "代码": quote.code,
                "价格": quote.price,
                "涨跌幅%": quote.pct,
                "时间": quote.time_text,
            }
            for quote in quotes.values()
        ]
    )


def _kline_figure(frame: pd.DataFrame, name: str) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Candlestick(
            x=frame["date"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name="K线",
        )
    )
    for column in ["ma20", "ma60"]:
        if column in frame.columns:
            figure.add_trace(go.Scatter(x=frame["date"], y=frame[column], mode="lines", name=column.upper()))
    figure.update_layout(
        title=name,
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return figure


def _fmt(value: object, suffix: str = "") -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value):.2f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _title() -> None:
    st.title("量化助手")
    st.caption("本地半自动复盘助手。只生成建议，不自动真实下单。")


page = st.sidebar.radio(
    "功能",
    ["总览", "历史 K 线", "信号 / ETF 排行", "回测", "导入持仓"],
    index=0,
)

_title()

if page == "总览":
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("基金资产", f'{fund["total_assets"]:,.2f}', f'{fund["today_pnl"]:,.2f}')
    col2.metric("股票资产", f'{stock["total_assets"]:,.2f}', f'{stock["today_pnl"]:,.2f}')
    col3.metric("股票可用", f'{stock["available_cash"]:,.2f}')
    col4.metric("计划总子弹", f'{config["cash_plan"]["available_cash_total"]:,.0f}')

    st.subheader("行情快照")
    st.caption(quote_status(config))
    load_quotes = st.button("刷新行情并重算建议", type="primary")
    if load_quotes:
        cached_quotes.clear()

    with st.spinner("正在获取行情..."):
        quotes, quote_messages = cached_quotes(config, portfolio)

    if quotes:
        latest_time = max((q.time_text for q in quotes.values() if q.time_text), default="")
        st.caption(f"行情更新时间: {latest_time or '未知'}")
        st.dataframe(_quote_frame(quotes), use_container_width=True, hide_index=True)
    else:
        st.warning("未获取到实时行情，策略将降级使用 portfolio.json 里的 last_daily_pct 快照值。")

    with st.expander("行情源状态", expanded=not bool(quotes)):
        for message in quote_messages:
            st.write(message)

    recs = generate_recommendations(config, portfolio, quotes=quotes)
    st.subheader("今日买卖清单（基于实时行情）" if quotes else "今日买卖清单（降级：使用持仓快照）")
    actions = action_list(recs)
    if actions.empty:
        st.info("当前没有触发明确买卖动作。")
    else:
        st.dataframe(actions, use_container_width=True, hide_index=True)
        st.download_button(
            "下载今日清单 CSV",
            actions.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"action-list-{date.today().isoformat()}.csv",
            mime="text/csv",
        )

    with st.expander("完整建议"):
        for rec in recs:
            st.write(f'**{rec["action"]}** `{rec["instrument"]}` `{rec["amount"]}`')
            st.caption(rec["reason"])

elif page == "历史 K 线":
    st.subheader("历史 K 线")
    name = st.selectbox("标的", list(options.keys()), index=0)
    col1, col2, col3 = st.columns(3)
    start_date = col1.date_input("开始日期", date.today() - timedelta(days=365))
    end_date = col2.date_input("结束日期", date.today())
    adjust = col3.selectbox("复权", ["qfq", "hfq", ""], index=0, format_func=lambda item: item or "不复权")

    if st.button("加载 K 线", type="primary"):
        with st.spinner("正在获取历史 K 线..."):
            history, messages = cached_history(options[name], start_date.isoformat(), end_date.isoformat(), adjust)
        if history.empty:
            st.warning("未获取到历史 K 线。")
        else:
            enriched = add_indicators(history)
            st.plotly_chart(_kline_figure(enriched, name), use_container_width=True)
            st.dataframe(enriched.tail(120), use_container_width=True, hide_index=True)
        with st.expander("历史数据源状态", expanded=history.empty):
            for message in messages:
                st.write(message)

elif page == "信号 / ETF 排行":
    st.subheader("均线 / 回撤信号")
    signal_name = st.selectbox("信号标的", list(options.keys()), index=min(1, len(options) - 1))
    if st.button("生成信号", type="primary"):
        with st.spinner("正在计算均线和回撤..."):
            signal_history, signal_messages = cached_history(
                options[signal_name],
                (date.today() - timedelta(days=540)).isoformat(),
                date.today().isoformat(),
                "qfq",
            )
        signal = latest_signal(signal_history)
        sig_col1, sig_col2, sig_col3, sig_col4 = st.columns(4)
        sig_col1.metric("信号", signal.get("signal", "-"))
        sig_col2.metric("收盘", _fmt(signal.get("close")))
        sig_col3.metric("MA20", _fmt(signal.get("ma20")))
        sig_col4.metric("20日回撤", _fmt(signal.get("drawdown_20_pct"), suffix="%"))
        st.caption(signal.get("reason", ""))
        with st.expander("信号数据源状态", expanded=signal_history.empty):
            for message in signal_messages:
                st.write(message)

    st.subheader("ETF 涨跌排行")
    ranking_limit = st.slider("排行数量", 10, 100, 30, step=10)
    if st.button("加载 ETF 排行"):
        with st.spinner("正在获取 ETF 排行..."):
            ranking, ranking_messages = cached_etf_ranking(ranking_limit)
        if ranking.empty:
            st.warning("未获取到 ETF 排行。")
        else:
            st.dataframe(ranking, use_container_width=True, hide_index=True)
        with st.expander("排行数据源状态", expanded=ranking.empty):
            for message in ranking_messages:
                st.write(message)

elif page == "回测":
    st.subheader("回测模块")
    bt_name = st.selectbox("回测标的", list(options.keys()), index=0)
    bt_col1, bt_col2, bt_col3, bt_col4 = st.columns(4)
    bt_start = bt_col1.date_input("回测开始", date.today() - timedelta(days=900))
    bt_end = bt_col2.date_input("回测结束", date.today())
    fast = bt_col3.number_input("快线 MA", min_value=5, max_value=120, value=20, step=5)
    slow = bt_col4.number_input("慢线 MA", min_value=20, max_value=250, value=60, step=10)

    if st.button("运行回测", type="primary"):
        with st.spinner("正在获取历史数据并回测..."):
            bt_history, bt_messages = cached_history(options[bt_name], bt_start.isoformat(), bt_end.isoformat(), "qfq")
            bt_curve, metrics = backtest_ma_trend(bt_history, int(fast), int(slow))
        if bt_curve.empty:
            st.warning("历史数据不足，无法回测。")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("策略收益", _fmt(metrics.get("strategy_return_pct"), "%"))
            m2.metric("持有收益", _fmt(metrics.get("buy_hold_return_pct"), "%"))
            m3.metric("最大回撤", _fmt(metrics.get("max_drawdown_pct"), "%"))
            m4.metric("交易次数", f'{metrics.get("trades", 0):.0f}')
            st.line_chart(bt_curve.set_index("date")[["equity", "buy_hold"]])
            st.dataframe(bt_curve.tail(120), use_container_width=True, hide_index=True)
        with st.expander("回测数据源状态", expanded=bt_curve.empty):
            for message in bt_messages:
                st.write(message)

elif page == "导入持仓":
    st.subheader("从表格导入持仓")
    template = template_frame()
    st.download_button(
        "下载持仓导入模板 CSV",
        template.to_csv(index=False).encode("utf-8-sig"),
        file_name="portfolio-template.csv",
        mime="text/csv",
    )
    table_file = st.file_uploader("上传 CSV / Excel", type=["csv", "xlsx", "xls"])
    if table_file is not None:
        raw = read_uploaded_table(table_file.name, table_file.getvalue())
        st.dataframe(raw, use_container_width=True)
        mapping = {}
        st.caption("字段映射。无法识别的列可以留空。")
        map_cols = st.columns(3)
        for index, target in enumerate(template.columns):
            mapping[target] = map_cols[index % 3].selectbox(
                target,
                [""] + list(raw.columns),
                key=f"map_{target}",
            )
        normalized = normalize_import_table(raw, mapping)
        positions = dataframe_to_positions(normalized)
        st.subheader("标准化结果")
        st.dataframe(normalized, use_container_width=True, hide_index=True)
        st.download_button(
            "下载标准化持仓 JSON",
            json.dumps(positions, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="imported-positions.json",
            mime="application/json",
        )

    st.subheader("从截图导入")
    image_file = st.file_uploader("上传截图 JPG / PNG", type=["jpg", "jpeg", "png"])
    if image_file is not None:
        st.image(image_file, caption="截图预览", use_container_width=True)
        st.caption("图片 OCR 结果会受券商页面排版影响。可先用手机/微信识别图片文字，再粘贴到下面解析。")

    ocr_text = st.text_area("粘贴截图 OCR 文本", height=160, placeholder="示例：半导体 200.30 100 2.003 -6.80 -3.28%")
    if st.button("解析截图文本") and ocr_text.strip():
        parsed = parse_ocr_positions(ocr_text)
        parsed_positions = dataframe_to_positions(parsed)
        if parsed.empty:
            st.warning("未识别到持仓行。建议保留：名称、市值、持股、现价、成本、盈亏率。")
        else:
            st.dataframe(parsed, use_container_width=True, hide_index=True)
            st.download_button(
                "下载截图解析 JSON",
                json.dumps(parsed_positions, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="screenshot-positions.json",
                mime="application/json",
            )

    with st.form("manual_position"):
        st.caption("截图无法自动识别时，可以先手动录入关键仓位。")
        c1, c2, c3, c4 = st.columns(4)
        manual_name = c1.text_input("名称")
        manual_tag = c2.selectbox("类型", ["wide_index", "tactical_ai", "power_grid", "military", "semiconductor", "robot", "imported"])
        manual_value = c3.number_input("市值/金额", min_value=0.0, value=0.0)
        manual_profit_pct = c4.number_input("持有收益率%", value=0.0)
        submitted = st.form_submit_button("生成持仓片段")
        if submitted and manual_name:
            st.json(
                {
                    "id": f"manual_{manual_name}",
                    "name": manual_name,
                    "tag": manual_tag,
                    "market_value": manual_value,
                    "holding_pnl_pct": manual_profit_pct,
                }
            )
