from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT if (ROOT / "src").exists() else ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_assistant.analytics import (
    add_advanced_indicators,
    add_indicators,
    backtest_ma_trend,
    interpret_backtest,
    latest_signal,
)
from quant_assistant.analytics_panel import (
    build_asset_distribution,
    compute_return_curve,
    compute_risk_metrics,
    compute_monthly_returns,
    load_portfolio_history,
)
from quant_assistant.auth import require_auth
from quant_assistant.data_source_health import read_health, summarize_by_provider
from quant_assistant.daily_brief import assess_quote_freshness, build_daily_cockpit, friendly_source_messages, is_trading_day
from quant_assistant.data_provider import build_provider, collect_secids, quote_status
from quant_assistant.user_data import get_or_create_portfolio, load_config, save_portfolio, user_history_file
from quant_assistant.importer import parse_ocr_import_text, update_account_from_import
from quant_assistant.commodity_chain import chain_summary, fetch_chain_prices, list_chains
from quant_assistant.macro_dashboard import fetch_macro_indicators, macro_summary
from quant_assistant.market_data import fetch_etf_ranking, fetch_history, instrument_options
from quant_assistant.market_scanner import DEFAULT_SCAN_LIMIT, scan_etfs
from quant_assistant.policy_radar import fetch_policy_news, summarize_policy_trends
from quant_assistant.recommendation_view import fund_holdings_table, recommendation_table, split_recommendations, stock_holdings_table
from quant_assistant.schema import blocking_issue_count as schema_blocking_issue_count, validate_app_data
from quant_assistant.strategy import generate_recommendations


st.set_page_config(page_title="Quant Assistant", layout="wide")

require_auth()

user = st.session_state.get("oauth_user", {})
portfolio = get_or_create_portfolio(user)
config = load_config(user)

data_issues = validate_app_data(config, portfolio)
if data_issues:
    blockers = schema_blocking_issue_count(data_issues)
    if blockers:
        st.error(f"配置/持仓数据存在 {blockers} 个阻断问题，应用已暂停。")
        st.dataframe(pd.DataFrame(data_issues), use_container_width=True, hide_index=True)
        st.stop()
    with st.expander("配置/持仓校验提示", expanded=False):
        st.dataframe(pd.DataFrame(data_issues), use_container_width=True, hide_index=True)

fund = portfolio["accounts"]["fund"]
stock = portfolio["accounts"]["stock"]
options = instrument_options(config)


def _current_user_id() -> str:
    provider = user.get("provider", "unknown")
    uid = user.get("id") or user.get("email", "anonymous")
    return f"{provider}_{uid}"


@st.cache_data(ttl=600, show_spinner=False)
def cached_quotes(user_id: str, config_json: str, secids_json: str):
    config_data = json.loads(config_json)
    secids = json.loads(secids_json)
    provider = build_provider(config_data)
    return provider.get_quotes_with_status(secids)


@st.cache_data(ttl=900, show_spinner=False)
def cached_history(secid: str, start_text: str, end_text: str, adjust: str) -> tuple[pd.DataFrame, list[str]]:
    return fetch_history(secid, date.fromisoformat(start_text), date.fromisoformat(end_text), adjust)


@st.cache_data(ttl=900, show_spinner=False)
def cached_etf_ranking(limit: int) -> tuple[pd.DataFrame, list[str]]:
    return fetch_etf_ranking(limit)


@st.cache_resource(show_spinner="正在加载 OCR 引擎...")
def _get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except ImportError:
        st.error(
            "OCR 引擎未安装。请运行以下命令安装可选依赖：\n\n"
            "`pip install -r requirements-ocr.txt`"
        )
        return None


def run_ocr(image_bytes: bytes) -> str:
    engine = _get_ocr_engine()
    if engine is None:
        return ""

    import numpy as np
    from PIL import Image

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    result, _ = engine(np.array(img))
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def reload_portfolio() -> None:
    global portfolio, fund, stock
    portfolio = get_or_create_portfolio(user)
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]
    cached_quotes.clear()


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
            label = "MA20" if column == "ma20" else "MA60"
            figure.add_trace(go.Scatter(x=frame["date"], y=frame[column], mode="lines", name=label))
    # Bollinger Bands
    for column in ["bb_upper", "bb_lower"]:
        if column in frame.columns:
            label = "布林上轨" if column == "bb_upper" else "布林下轨"
            figure.add_trace(
                go.Scatter(
                    x=frame["date"],
                    y=frame[column],
                    mode="lines",
                    name=label,
                    line=dict(dash="dash", width=1),
                )
            )
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
    ["总览", "历史 K 线", "信号 / ETF 排行", "回测", "导入持仓", "分析", "市场扫描", "宏观/产业"],
    index=0,
)

_title()

if page == "总览":
    col1, col2 = st.columns(2)
    col1.metric("基金资产", f'{fund["total_assets"]:,.2f}', f'{fund["today_pnl"]:,.2f}')
    col2.metric("股票资产", f'{stock["total_assets"]:,.2f}', f'{stock["today_pnl"]:,.2f}')

    st.subheader("我的持仓数据")
    btn_col1, btn_col2 = st.columns(2)
    load_quotes = btn_col1.button("刷新行情并重算建议", type="primary")
    if btn_col2.button("从文件刷新持仓"):
        reload_portfolio()
        st.rerun()
    if load_quotes:
        cached_quotes.clear()
        st.rerun()

    with st.spinner("正在获取行情..."):
        secids = collect_secids(config, portfolio)
        quotes, quote_messages = cached_quotes(_current_user_id(), json.dumps(config), json.dumps(sorted(set(secids))))

    quote_freshness = assess_quote_freshness([q.time_text for q in quotes.values() if q.time_text])

    health_records = read_health(days=7)
    health_summary = summarize_by_provider(health_records) if health_records else None
    recs = generate_recommendations(config, portfolio, quotes=quotes, data_source_health=health_summary, is_trading_day=is_trading_day())
    data_source = "实时行情" if quotes else "持仓快照"
    actionable_recs, watchlist_recs = split_recommendations(recs)

    st.subheader("今日操作清单（基于实时行情）" if quotes else "今日操作清单（降级：使用持仓快照）")
    actions = recommendation_table(actionable_recs, data_source)
    if actions.empty:
        st.info("当前没有触发买入、卖出或限价买入动作。")
    else:
        st.dataframe(actions, use_container_width=True, hide_index=True)
        st.download_button(
            "下载今日清单 CSV",
            actions.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"action-list-{date.today().isoformat()}.csv",
            mime="text/csv",
        )

    with st.expander(f"观察项（HOLD，共 {len(watchlist_recs)} 条）", expanded=False):
        watchlist = recommendation_table(watchlist_recs, data_source)
        if watchlist.empty:
            st.info("暂无观察项。")
        else:
            st.dataframe(watchlist, use_container_width=True, hide_index=True)

    fund_holdings = fund_holdings_table(portfolio)
    stock_holdings = stock_holdings_table(portfolio)
    st.markdown("##### 基金持仓")
    if fund_holdings.empty:
        st.info("当前没有基金持仓数据。")
    else:
        st.dataframe(fund_holdings, use_container_width=True, hide_index=True)

    st.markdown("##### 股票持仓")
    if stock_holdings.empty:
        st.info("当前没有股票持仓数据。")
    else:
        st.dataframe(stock_holdings, use_container_width=True, hide_index=True)

    with st.expander("行情源状态", expanded=not bool(quotes)):
        st.caption(quote_status(config))
        if quotes:
            latest_time = max((q.time_text for q in quotes.values() if q.time_text), default="")
            st.write(f"行情更新时间: {latest_time or '未知'}")
        else:
            st.warning("未获取到实时行情，策略将降级使用 portfolio.json 里的 last_daily_pct 快照值。")
        if quote_freshness["reliable"]:
            st.info(f'{quote_freshness["status"]}：{quote_freshness["detail"]}')
        else:
            st.warning(f'{quote_freshness["status"]}：{quote_freshness["detail"]}')
        for message in friendly_source_messages(quote_messages):
            st.write(message)

        # Data source health summary
        if health_records:
            st.divider()
            st.caption("数据源健康度（近7天）")
            health_summary = summarize_by_provider(health_records)
            for provider, stats in health_summary.items():
                rate = stats["success_rate"]
                latency = stats["avg_latency_ms"]
                total = stats["total_requests"]
                st.write(
                    f"**{provider}**: 成功率 {rate:.1f}%, 平均延迟 {latency:.0f}ms, 总请求 {total:.0f}"
                )

    st.subheader("今日驾驶舱")
    st.caption("只做复盘、条件检查和人工复核提示，不预测未来涨跌，不自动下单。")
    cockpit_rows = build_daily_cockpit(
        data_reliable=bool(quote_freshness["reliable"]),
        data_detail=str(quote_freshness["detail"]),
        actionable_count=len(actionable_recs),
        watchlist_count=len(watchlist_recs),
        coverage_issue_count=0,
    )
    st.dataframe(pd.DataFrame(cockpit_rows), use_container_width=True, hide_index=True)

    with st.expander("完整建议原文"):
        for rec in recs:
            st.write(f'**{rec["action"]}** `{rec["instrument"]}` `{rec["amount"]}`')
            st.caption(rec["reason"])

    # Change history panel
    with st.expander("持仓变更记录"):
        from quant_assistant.history import read_history, rollback

        history_file = user_history_file(user)
        history = read_history(history_file, limit=10)

        if not history:
            st.info("暂无变更记录。导入持仓后会自动记录。")
        else:
            for record in history:
                ts = record.get("timestamp", "")[:16].replace("T", " ")
                account = "股票" if record.get("account") == "stock" else "基金"
                changes = record.get("changes", {})
                added = changes.get("added", [])
                updated = changes.get("updated", [])
                removed = changes.get("removed", [])

                parts = []
                if added:
                    parts.append(f"新增 {len(added)} 条")
                if updated:
                    parts.append(f"更新 {len(updated)} 条")
                if removed:
                    parts.append(f"移除 {len(removed)} 条")

                summary_text = "，".join(parts) if parts else "无变更"
                st.write(f"**{ts}** | {account} | {record.get('type', 'unknown')} | {summary_text}")

                detail_parts = []
                if added:
                    detail_parts.append(f"新增: {', '.join(added)}")
                if updated:
                    detail_parts.append(f"更新: {', '.join(updated)}")
                if removed:
                    detail_parts.append(f"移除: {', '.join(removed)}")
                if detail_parts:
                    st.caption("  ".join(detail_parts))

            # Rollback button
            st.divider()
            if st.button("撤销上次导入", help="恢复到上一次导入前的持仓状态"):
                restored = rollback(history_file)
                if restored:
                    account_key = history[0].get("account") if history else None
                    if account_key and account_key in portfolio["accounts"]:
                        portfolio["accounts"][account_key] = restored
                        portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        save_portfolio(user, portfolio)
                        reload_portfolio()
                        st.success(f"已撤销上次导入，{account_key} 持仓已恢复。")
                        st.rerun()
                else:
                    st.warning("无可用的历史记录用于撤销。")

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
            enriched = add_advanced_indicators(enriched)
            st.plotly_chart(_kline_figure(enriched, name), use_container_width=True)
            display_cols = {
                "date": "日期", "open": "开盘", "high": "最高", "low": "最低",
                "close": "收盘", "volume": "成交量", "amount": "成交额",
                "ma5": "MA5", "ma20": "MA20", "ma60": "MA60",
                "macd": "MACD", "macd_signal": "MACD信号", "macd_hist": "MACD柱状",
                "rsi14": "RSI14", "bb_upper": "布林上轨", "bb_lower": "布林下轨", "bb_middle": "布林中轨",
                "high_20": "20日最高", "drawdown_20_pct": "20日回撤%", "drawdown_pct": "最大回撤%",
            }
            display_frame = enriched.rename(columns={k: v for k, v in display_cols.items() if k in enriched.columns})
            st.dataframe(display_frame.tail(120), use_container_width=True, hide_index=True)
        with st.expander("历史数据源状态", expanded=history.empty):
            for message in friendly_source_messages(messages):
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
            for message in friendly_source_messages(signal_messages):
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
            for message in friendly_source_messages(ranking_messages):
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
            m1.metric("策略收益", _fmt(metrics.get("策略收益"), "%"))
            m2.metric("持有收益", _fmt(metrics.get("持有收益"), "%"))
            m3.metric("最大回撤", _fmt(metrics.get("最大回撤"), "%"))
            m4.metric("交易次数", f'{metrics.get("交易次数", 0):.0f}')
            interpretation = interpret_backtest(metrics)
            note = f'{interpretation["结论"]}：{interpretation["建议"]}'
            if interpretation["结论"] == "跑输持有":
                st.warning(note)
            else:
                st.info(note)
            st.caption("回测只解释历史样本内表现，不代表未来收益。")
            st.line_chart(bt_curve.set_index("日期")[["策略净值", "持有净值"]])
            st.dataframe(bt_curve.tail(120), use_container_width=True, hide_index=True)
        with st.expander("回测数据源状态", expanded=bt_curve.empty):
            for message in friendly_source_messages(bt_messages):
                st.write(message)

elif page == "导入持仓":
    st.subheader("截图 OCR 导入")

    account_labels = {"fund": "支付宝基金 (fund)", "stock": "国信证券 (stock)"}
    selected_account = st.radio(
        "目标账户",
        ["fund", "stock"],
        horizontal=True,
        format_func=lambda item: account_labels[item],
        key="ocr_target_account",
    )

    image_file = st.file_uploader(
        "上传截图 JPG / PNG",
        type=["jpg", "jpeg", "png"],
        key="single_screenshot",
    )
    if st.button("识别截图", type="primary", disabled=image_file is None):
        if image_file is not None:
            with st.spinner("正在识别截图..."):
                st.session_state["ocr_text_input"] = run_ocr(image_file.getvalue())
            for key in ("ocr_import_parsed", "ocr_import_summary", "ocr_import_positions"):
                st.session_state.pop(key, None)

    ocr_text = st.text_area(
        "OCR 文本",
        key="ocr_text_input",
        height=260,
        placeholder="上传截图识别，或直接粘贴手机 OCR 文本。",
    )

    if st.button("解析文本", disabled=not str(ocr_text).strip()):
        parsed, summary, parsed_positions = parse_ocr_import_text(str(ocr_text))
        st.session_state["ocr_import_parsed"] = parsed
        st.session_state["ocr_import_summary"] = summary
        st.session_state["ocr_import_positions"] = parsed_positions

    parsed = st.session_state.get("ocr_import_parsed")
    summary = st.session_state.get("ocr_import_summary")
    parsed_positions = st.session_state.get("ocr_import_positions", [])

    if parsed is not None:
        if summary:
            summary_frame = pd.DataFrame([summary]).dropna(axis=1, how="all")
            if not summary_frame.empty:
                st.dataframe(summary_frame, use_container_width=True, hide_index=True)

        if parsed.empty:
            st.warning("未识别到持仓行。")
        else:
            st.dataframe(parsed, use_container_width=True, hide_index=True)

            from quant_assistant.history import compute_delta

            target_account = portfolio["accounts"][selected_account]
            delta = compute_delta(target_account.get("positions", []), parsed_positions)

            diff_parts = []
            if delta.get("added"):
                diff_parts.append(f"新增 {len(delta['added'])} 条: {', '.join(delta['added'][:5])}")
            if delta.get("updated"):
                diff_parts.append(f"更新 {len(delta['updated'])} 条: {', '.join(delta['updated'][:5])}")
            if delta.get("removed"):
                diff_parts.append(f"移除 {len(delta['removed'])} 条: {', '.join(delta['removed'][:5])}")

            if diff_parts:
                preview_text = " | ".join(diff_parts)
                st.info(f"写入后将变更：{preview_text}")
            else:
                st.info("解析结果与当前持仓一致，无变更。")

            if st.button("确认写入", type="primary", key="ocr_update_btn"):
                from quant_assistant.history import record_change

                previous_snapshot = dict(target_account)

                updated_account = update_account_from_import(
                    target_account,
                    parsed_positions,
                    selected_account,
                    summary,
                )
                merged_positions = updated_account["positions"]
                portfolio["accounts"][selected_account] = updated_account
                portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                account_summary = {
                    "total_assets": updated_account.get("total_assets"),
                    "total_positions": len(merged_positions),
                }
                record_change(
                    user_history_file(user),
                    change_type="ocr_import",
                    account=selected_account,
                    delta=delta,
                    summary=account_summary,
                    previous_snapshot=previous_snapshot,
                )

                save_portfolio(user, portfolio)
                reload_portfolio()
                for key in ("ocr_import_parsed", "ocr_import_summary", "ocr_import_positions", "ocr_text_input"):
                    st.session_state.pop(key, None)
                st.success(f"已更新 {account_labels[selected_account]}，共 {len(merged_positions)} 条持仓。")
                st.rerun()

elif page == "分析":
    st.subheader("资产分布")
    dist = build_asset_distribution(portfolio)
    if not dist.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(dist, values="market_value", names="tag", title="按策略类型")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.pie(dist, values="market_value", names="account", title="按账户")
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("暂无持仓数据。")

    st.subheader("累计收益曲线")
    history_file = user_history_file(user)
    hist_df = load_portfolio_history(history_file)
    if not hist_df.empty and len(hist_df) >= 2:
        curve = compute_return_curve(hist_df)
        if not curve.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=curve["timestamp"], y=curve["cumulative_return_pct"],
                mode="lines", name="累计收益%"
            ))
            fig.update_layout(title="累计收益走势", yaxis_title="收益率%")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("收益数据不足。")
    else:
        st.info("持续导入持仓以生成收益曲线。")

    st.subheader("风险指标")
    metrics = compute_risk_metrics(hist_df)
    if metrics:
        m1, m2, m3 = st.columns(3)
        m1.metric("最大回撤", f"{metrics['max_drawdown_pct']:.2f}%")
        m2.metric("年化波动率", f"{metrics['annual_volatility_pct']:.2f}%")
        m3.metric("夏普比率", f"{metrics['sharpe_ratio']:.2f}")
    else:
        st.info("数据不足，无法计算风险指标。")

    st.subheader("月度收益")
    monthly = compute_monthly_returns(hist_df)
    if not monthly.empty:
        pivot = monthly.pivot(index="year", columns="month", values="return_pct")
        fig = px.imshow(
            pivot,
            labels=dict(x="月份", y="年份", color="收益率%"),
            color_continuous_scale="RdYlGn",
            aspect="auto",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("数据不足，无法生成月度收益热力图。")

elif page == "市场扫描":
    st.subheader("全市场 ETF 多因子扫描")
    st.caption("基于动量、趋势、RSI、MACD、成交量等因子综合评分，不预测未来，只反映当前技术面强弱。")
    scan_col1, scan_col2 = st.columns([1, 3])
    scan_limit = scan_col1.number_input("扫描数量", min_value=10, max_value=500, value=DEFAULT_SCAN_LIMIT, step=10)
    scan_col2.caption("默认只扫前 30 只流动性最高 ETF，重复扫描优先命中本地缓存。")
    btn_col1, btn_col2 = scan_col2.columns([1, 1])
    if btn_col1.button("开始扫描", type="primary"):
        with st.spinner(f"正在扫描前 {scan_limit} 只流动性最高的 ETF..."):
            scan_result, scan_messages = scan_etfs(top_n=scan_limit)
    elif btn_col2.button("强制刷新（跳过缓存）"):
        with st.spinner(f"正在扫描前 {scan_limit} 只流动性最高的 ETF...（跳过缓存）"):
            scan_result, scan_messages = scan_etfs(top_n=scan_limit, force_refresh=True)
    else:
        scan_result = None
    if scan_result is not None:
        if scan_result.empty:
            st.warning("扫描未返回数据。")
        else:
            st.success(f"扫描完成，综合评分排名前 {len(scan_result)}：")
            display_cols = ["排名", "代码", "名称", "价格", "综合评分", "5日涨幅%", "20日涨幅%", "60日涨幅%", "趋势分(0-3)", "RSI", "20日回撤%", "量比"]
            available_cols = [c for c in display_cols if c in scan_result.columns]
            st.dataframe(scan_result[available_cols], use_container_width=True, hide_index=True)
        with st.expander("扫描状态"):
            for msg in friendly_source_messages(scan_messages):
                st.write(msg)

elif page == "宏观/产业":
    st.subheader("全球宏观仪表盘")
    if st.button("刷新宏观数据", type="primary"):
        from quant_assistant.macro_dashboard import MACRO_CACHE_KEY
        from quant_assistant.disk_cache import save_generic_cache
        save_generic_cache(MACRO_CACHE_KEY, None)
    with st.spinner("正在获取宏观数据..."):
        macro_data, macro_messages = fetch_macro_indicators()
    if macro_data:
        mc1, mc2, mc3, mc4 = st.columns([1, 1, 1.3, 1])
        if macro_data.get("cn_10y_bond") is not None:
            mc1.metric("中国10债", f"{macro_data['cn_10y_bond']:.2f}%")
        if macro_data.get("us_10y_bond") is not None:
            mc2.metric("美国10债", f"{macro_data['us_10y_bond']:.2f}%")
        if macro_data.get("cn_us_spread") is not None:
            mc3.metric("中美利差", f"{macro_data['cn_us_spread']:.2f}%")
        if macro_data.get("usdcny") is not None:
            mc4.metric("美元兑人民币", f"{macro_data['usdcny']:.4f}")
        mc5, mc6, mc7, mc8 = st.columns(4)
        if macro_data.get("cn_pmi") is not None:
            mc5.metric("中国PMI", f"{macro_data['cn_pmi']:.1f}")
        if macro_data.get("cn_cpi_yoy") is not None:
            mc6.metric("中国CPI", f"{macro_data['cn_cpi_yoy']:.2f}%")
        if macro_data.get("us_cpi_yoy") is not None:
            mc7.metric("美国CPI", f"{macro_data['us_cpi_yoy']:.2f}%")
        if macro_data.get("fed_rate") is not None:
            mc8.metric("美联储利率", f"{macro_data['fed_rate']:.2f}%")

        st.divider()
        st.caption("宏观解读")
        summaries = macro_summary(macro_data)
        for s in summaries:
            st.write(f"**{s['指标']}** | {s['状态']} | {s['解读']}")
    else:
        st.info("宏观数据暂不可用，可能因 AkShare 网络或本地环境问题。")
    with st.expander("宏观数据状态"):
        for msg in friendly_source_messages(macro_messages):
            st.write(msg)

    st.divider()
    st.subheader("产业链跟踪")
    chain_name = st.selectbox("选择产业链", list_chains())
    if chain_name:
        chain_info = chain_summary(chain_name)
        if chain_info:
            st.caption(chain_info["description"])
        if st.button("刷新产业链数据", type="primary"):
            from quant_assistant.disk_cache import save_generic_cache
            save_generic_cache(f"chain_{chain_name}", None)
            st.rerun()
        with st.spinner("正在获取价格数据..."):
            chain_prices, chain_messages = fetch_chain_prices(chain_name)
        if chain_prices:
            st.dataframe(pd.DataFrame(chain_prices), use_container_width=True, hide_index=True)
        else:
            st.info("价格数据暂不可用。")
        with st.expander("价格数据源状态"):
            for msg in friendly_source_messages(chain_messages):
                st.write(msg)

    st.divider()
    st.subheader("政策雷达")
    if st.button("刷新政策新闻"):
        from quant_assistant.disk_cache import save_generic_cache
        save_generic_cache("policy_news_50", None)
    with st.spinner("正在抓取政策新闻..."):
        news_df, news_messages = fetch_policy_news(limit=50)
    if not news_df.empty:
        policy_df = news_df[news_df["is_policy"] == True]
        st.caption(f"共 {len(news_df)} 条新闻，其中 {len(policy_df)} 条与关注主题相关")
        if not policy_df.empty:
            st.dataframe(policy_df[["title", "time", "tags", "source"]].head(20), use_container_width=True, hide_index=True)
            trends = summarize_policy_trends(news_df, top_n=10)
            if trends:
                st.caption("热门政策主题")
                st.dataframe(pd.DataFrame(trends), use_container_width=True, hide_index=True)
        else:
            st.info("近期暂无匹配的政策新闻。")
    else:
        st.info("新闻数据暂不可用。")
    with st.expander("新闻抓取状态"):
        for msg in friendly_source_messages(news_messages):
            st.write(msg)

