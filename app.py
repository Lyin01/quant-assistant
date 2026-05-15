from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.analytics import action_list, add_indicators, backtest_ma_trend, latest_signal
from quant_assistant.config import load_json, save_json
from quant_assistant.data_provider import build_provider, collect_secids, quote_status
from quant_assistant.importer import (
    dataframe_to_positions,
    merge_account_summary,
    merge_positions,
    normalize_import_table,
    parse_ocr_positions,
    parse_ocr_summary,
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


@st.cache_resource(show_spinner="正在加载 OCR 引擎...")
def _get_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def run_ocr(image_bytes: bytes) -> str:
    import numpy as np
    from PIL import Image

    engine = _get_ocr_engine()
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    result, _ = engine(np.array(img))
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def reload_portfolio() -> None:
    global portfolio, fund, stock
    portfolio = load_json(ROOT / "portfolio.json")
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]
    cached_quotes.clear()


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
    btn_col1, btn_col2 = st.columns(2)
    load_quotes = btn_col1.button("刷新行情并重算建议", type="primary")
    if btn_col2.button("从文件刷新持仓"):
        reload_portfolio()
        st.rerun()
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
        st.divider()
        st.subheader("更新到总览")
        csv_has_shares = any(p.get("shares") for p in positions)
        csv_detected = "stock" if csv_has_shares else "fund"
        csv_account_choice = st.selectbox(
            "目标账户",
            ["fund", "stock"],
            index=0 if csv_detected == "fund" else 1,
            format_func=lambda x: "支付宝基金 (fund)" if x == "fund" else "国信证券 (stock)",
            key="csv_account_select",
        )
        if st.button("确认更新持仓", type="primary", key="csv_update_btn"):
            target = portfolio["accounts"][csv_account_choice]
            merged = merge_positions(target["positions"], positions)
            target["positions"] = merged
            portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_json(ROOT / "portfolio.json", portfolio)
            reload_portfolio()
            st.success(f"已更新 {csv_account_choice} 持仓，共 {len(merged)} 条。")
            st.rerun()

    st.subheader("从截图导入")
    image_col, ocr_col = st.columns([1, 2])
    with image_col:
        image_file = st.file_uploader("上传截图 JPG / PNG", type=["jpg", "jpeg", "png"])
        if image_file is not None:
            st.image(image_file, caption="截图预览", width=320)

    ocr_prefill = ""
    if image_file is not None:
        image_bytes = image_file.getvalue()
        with st.spinner("正在识别截图文字..."):
            ocr_prefill = run_ocr(image_bytes)
        if ocr_prefill:
            st.success(f"OCR 已识别 {len(ocr_prefill)} 个字符，可编辑后解析。")
        else:
            st.warning("OCR 未识别到文字，请手动粘贴。")

    with ocr_col:
        with st.form("ocr_import_form"):
            preset = st.selectbox("解析格式", ["股票截图", "基金截图", "通用"], index=0)
            ocr_text = st.text_area(
                "截图 OCR 文本（自动识别或手动粘贴）",
                value=ocr_prefill,
                height=180,
                placeholder=(
                    "股票：半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%\n"
                    "基金：易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%"
                ),
            )
            parse_submitted = st.form_submit_button("解析截图文本", type="primary")

        if parse_submitted:
            if not ocr_text.strip():
                st.warning("请先粘贴截图 OCR 文本。")
            else:
                parsed = parse_ocr_positions(ocr_text)
                summary = parse_ocr_summary(f"{preset}\n{ocr_text}")
                st.session_state["ocr_import_parsed"] = parsed
                st.session_state["ocr_import_summary"] = summary
                st.session_state["ocr_import_positions"] = dataframe_to_positions(parsed)

        parsed = st.session_state.get("ocr_import_parsed")
        summary = st.session_state.get("ocr_import_summary")
        parsed_positions = st.session_state.get("ocr_import_positions", [])
        if parsed is not None:
            if summary:
                summary_frame = pd.DataFrame([summary]).dropna(axis=1, how="all")
                if not summary_frame.empty:
                    st.dataframe(summary_frame, use_container_width=True, hide_index=True)
            if parsed.empty:
                st.warning("未识别到持仓行。建议保留：名称、市值、持股、现价、成本、盈亏率。")
            else:
                st.success(f"已识别 {len(parsed)} 条持仓。")
                st.dataframe(parsed, use_container_width=True, hide_index=True)
                st.download_button(
                    "下载截图解析 JSON",
                    json.dumps(parsed_positions, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name="screenshot-positions.json",
                    mime="application/json",
                )

                st.divider()
                st.subheader("更新到总览")
                detected_account = summary.get("account_type") if summary else None
                if not detected_account:
                    has_shares = any(p.get("shares") for p in parsed_positions)
                    detected_account = "stock" if has_shares else "fund"
                account_choice = st.selectbox(
                    "目标账户",
                    ["fund", "stock"],
                    index=0 if detected_account == "fund" else 1,
                    format_func=lambda x: "支付宝基金 (fund)" if x == "fund" else "国信证券 (stock)",
                    key="ocr_account_select",
                )
                target_account = portfolio["accounts"][account_choice]
                existing_names = {p["name"] for p in target_account["positions"]}
                imported_names = {p["name"] for p in parsed_positions}
                update_names = existing_names & imported_names
                new_names = imported_names - existing_names
                with st.expander("变更预览", expanded=True):
                    if update_names:
                        st.write("更新数值:", ", ".join(update_names))
                    if new_names:
                        st.write("新增持仓:", ", ".join(new_names))
                    st.write("保留不动:", ", ".join(existing_names - imported_names) if (existing_names - imported_names) else "无")
                    if summary:
                        st.json({k: v for k, v in summary.items() if v is not None and k != "account_type"})
                if st.button("确认更新持仓", type="primary", key="ocr_update_btn"):
                    merged_positions = merge_positions(target_account["positions"], parsed_positions)
                    if summary:
                        updated_account = merge_account_summary(target_account, summary)
                    else:
                        updated_account = dict(target_account)
                    updated_account["positions"] = merged_positions
                    portfolio["accounts"][account_choice] = updated_account
                    portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_json(ROOT / "portfolio.json", portfolio)
                    reload_portfolio()
                    for key in ("ocr_import_parsed", "ocr_import_summary", "ocr_import_positions"):
                        st.session_state.pop(key, None)
                    st.success(f"已更新 {account_choice} 持仓，共 {len(merged_positions)} 条。")
                    st.rerun()

        with st.expander("推荐粘贴格式", expanded=False):
            st.code(
                """# 股票截图：国信证券
总资产: 6245.08
今日盈亏: -40.00
持仓盈亏: -15.22
总市值: 4600.80
可用: 1644.28
沃尔核材 | 2249.00 | 100 | 100 | 22.490 | 23.000 | -51.02 | -2.22%
纳指大成 | 1559.70 | 900 | 900 | 1.733 | 1.725 | +7.60 | +0.49%
创新药 | 239.40 | 300 | 300 | 0.798 | 0.825 | -8.00 | -3.23%
半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%

# 基金截图：支付宝
账户资产: 18118.73
场内穿透: -228.25
博时标普500ETF联接 | 109.18 | +0.77% | +9.18 | +9.18%
华宝纳斯达克精选 | 3145.75 | +0.97% | +269.53 | +9.37%
易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%
天弘中证人工智能定投小仓 | 459.98 | -2.26% | +59.98 | +14.99%
天弘中证人工智能大仓 | 1717.05 | -2.26% | +264.36 | +18.20%
广发中证军工ETF联接 | 1375.92 | -2.35% | -94.17 | -6.41%
天弘中证电网设备 | 3270.40 | -3.24% | +363.23 | +12.49%""",
                language="text",
            )

    with st.form("manual_position"):
        st.caption("手动录入持仓，提交后直接写入总览。")
        c1, c2, c3, c4 = st.columns(4)
        manual_name = c1.text_input("名称")
        manual_tag = c2.selectbox("类型", ["wide_index", "tactical_ai", "power_grid", "military", "semiconductor", "robot", "overseas", "healthcare", "defensive", "core_ai_dca", "imported"])
        manual_value = c3.number_input("市值/金额", min_value=0.0, value=0.0)
        manual_profit_pct = c4.number_input("持有收益率%", value=0.0)
        manual_account = st.selectbox("目标账户", ["fund", "stock"], format_func=lambda x: "支付宝基金 (fund)" if x == "fund" else "国信证券 (stock)")
        submitted = st.form_submit_button("添加到持仓", type="primary")
        if submitted and manual_name:
            new_position = {
                "id": f"manual_{manual_name}",
                "name": manual_name,
                "tag": manual_tag,
                "market_value": manual_value,
                "holding_pnl_pct": manual_profit_pct,
            }
            target = portfolio["accounts"][manual_account]
            merged = merge_positions(target["positions"], [new_position])
            target["positions"] = merged
            portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_json(ROOT / "portfolio.json", portfolio)
            reload_portfolio()
            st.success(f"已添加 {manual_name} 到 {manual_account}，共 {len(merged)} 条持仓。")
            st.rerun()
