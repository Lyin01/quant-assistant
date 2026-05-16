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
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.analytics import action_list, add_advanced_indicators, add_indicators, backtest_ma_trend, latest_signal
from quant_assistant.analytics_panel import (
    build_asset_distribution,
    compute_return_curve,
    compute_risk_metrics,
    compute_monthly_returns,
    load_portfolio_history,
)
from quant_assistant.auth import require_auth
from quant_assistant.data_source_health import read_health, summarize_by_provider
from quant_assistant.data_provider import build_provider, collect_secids, quote_status
from quant_assistant.user_data import get_or_create_portfolio, load_config, save_portfolio, user_history_file
from quant_assistant.importer import (
    _infer_tag,
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

require_auth()

user = st.session_state.get("oauth_user", {})
portfolio = get_or_create_portfolio(user)
config = load_config(user)
fund = portfolio["accounts"]["fund"]
stock = portfolio["accounts"]["stock"]
options = instrument_options(config)


def _current_user_id() -> str:
    provider = user.get("provider", "unknown")
    uid = user.get("id") or user.get("email", "anonymous")
    return f"{provider}_{uid}"


@st.cache_data(ttl=600, show_spinner=False)
def cached_quotes(user_id: str, config_json: str, portfolio_json: str):
    config_data = json.loads(config_json)
    portfolio_data = json.loads(portfolio_json)
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
    portfolio = get_or_create_portfolio(user)
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


def _merge_parsed_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple parsed DataFrames, keeping the latest row for duplicate names."""
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty or "name" not in combined.columns:
        return combined
    return combined.drop_duplicates(subset=["name"], keep="last").reset_index(drop=True)


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
    # Bollinger Bands
    for column in ["bb_upper", "bb_lower"]:
        if column in frame.columns:
            label = "BB Upper" if column == "bb_upper" else "BB Lower"
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
    ["总览", "历史 K 线", "信号 / ETF 排行", "回测", "导入持仓", "分析"],
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
        quotes, quote_messages = cached_quotes(_current_user_id(), json.dumps(config), json.dumps(portfolio))

    if quotes:
        latest_time = max((q.time_text for q in quotes.values() if q.time_text), default="")
        st.caption(f"行情更新时间: {latest_time or '未知'}")
        st.dataframe(_quote_frame(quotes), use_container_width=True, hide_index=True)
    else:
        st.warning("未获取到实时行情，策略将降级使用 portfolio.json 里的 last_daily_pct 快照值。")

    with st.expander("行情源状态", expanded=not bool(quotes)):
        for message in quote_messages:
            st.write(message)

        # Data source health summary
        health_records = read_health(days=7)
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
            from quant_assistant.history import compute_delta, record_change

            target = portfolio["accounts"][csv_account_choice]
            previous_snapshot = dict(target)

            merged = merge_positions(target["positions"], positions)
            target["positions"] = merged
            portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            delta = compute_delta(previous_snapshot.get("positions", []), positions)
            account_summary = {
                "total_assets": target.get("total_assets"),
                "total_positions": len(merged),
            }
            record_change(
                user_history_file(user),
                change_type="csv_import",
                account=csv_account_choice,
                delta=delta,
                summary=account_summary,
                previous_snapshot=previous_snapshot,
            )

            save_portfolio(user, portfolio)
            reload_portfolio()
            st.success(f"已更新 {csv_account_choice} 持仓，共 {len(merged)} 条。变更已记录到历史。")
            st.rerun()

    st.subheader("从截图导入")

    import_mode = st.radio(
        "导入模式",
        options=["截图识别", "纯文本粘贴"],
        index=0,
        horizontal=True,
        key="import_mode",
    )

    ocr_prefill = ""

    if import_mode == "截图识别":
        image_files = st.file_uploader(
            "上传截图 JPG / PNG（可多选）",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="multi_screenshot",
        )
        if image_files:
            all_parsed: list[pd.DataFrame] = []
            image_col, text_col = st.columns([1, 2])
            for idx, image_file in enumerate(image_files):
                with image_col:
                    st.image(image_file, caption=f"截图 {idx + 1}", width=240)
                image_bytes = image_file.getvalue()
                with st.spinner(f"正在识别截图 {idx + 1}..."):
                    recognized = run_ocr(image_bytes)
                if recognized:
                    parsed = parse_ocr_positions(recognized)
                    if not parsed.empty:
                        all_parsed.append(parsed)
                else:
                    st.warning(f"截图 {idx + 1} 未识别到文字。")

            if all_parsed:
                merged_parsed = _merge_parsed_frames(all_parsed)
                with text_col:
                    st.success(f"共识别 {len(merged_parsed)} 条持仓，可编辑后确认。")
                    edited = st.data_editor(
                        merged_parsed,
                        use_container_width=True,
                        hide_index=True,
                        key="ocr_editor",
                    )
                    # Convert edited DataFrame back to text for the form below
                    ocr_prefill = "\n".join(
                        " | ".join(str(v) for v in row if pd.notna(v))
                        for _, row in edited.iterrows()
                    )
            else:
                st.info("未从截图中识别到有效持仓，请切换到纯文本粘贴模式手动输入。")

    if import_mode == "纯文本粘贴" or ocr_prefill:
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
            parse_submitted = st.form_submit_button("解析并预览", type="primary")

        if parse_submitted and ocr_text.strip():
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

            # Tag assignment for new positions
            detected_account = summary.get("account_type") if summary else None
            if not detected_account:
                has_shares = any(p.get("shares") for p in parsed_positions)
                detected_account = "stock" if has_shares else "fund"

            target_account = portfolio["accounts"][detected_account]
            existing_names = {p["name"] for p in target_account["positions"]}
            imported_names = {p["name"] for p in parsed_positions}
            new_names = imported_names - existing_names
            update_names = existing_names & imported_names

            # Tag selection for new holdings
            tag_choices = [
                "wide_index", "tactical_ai", "power_grid", "military",
                "semiconductor", "robot", "overseas", "healthcare",
                "defensive", "core_ai_dca", "imported"
            ]
            if new_names:
                st.subheader("为新持仓选择策略标签")
                for pos in parsed_positions:
                    if pos["name"] in new_names:
                        suggested = _infer_tag(pos["name"])
                        idx = tag_choices.index(suggested) if suggested in tag_choices else tag_choices.index("imported")
                        pos["tag"] = st.selectbox(
                            f"`{pos['name']}` 的策略标签",
                            tag_choices,
                            index=idx,
                            key=f"tag_select_{pos['name']}",
                        )

            st.divider()
            st.subheader("变更预览")
            preview_cols = st.columns(3)
            with preview_cols[0]:
                st.metric("新增", len(new_names))
            with preview_cols[1]:
                st.metric("更新", len(update_names))
            with preview_cols[2]:
                st.metric("保留", len(existing_names - imported_names))

            with st.expander("详细对比", expanded=True):
                if new_names:
                    st.write("新增:", ", ".join(new_names))
                if update_names:
                    st.write("更新:", ", ".join(update_names))
                unchanged = existing_names - imported_names
                if unchanged:
                    st.write("保留:", ", ".join(unchanged))

            # History tracking integration
            from quant_assistant.history import compute_delta, record_change

            if st.button("确认更新持仓", type="primary", key="ocr_update_btn"):
                # Save snapshot before change
                previous_snapshot = dict(target_account)

                merged_positions = merge_positions(target_account["positions"], parsed_positions)
                if summary:
                    updated_account = merge_account_summary(target_account, summary)
                else:
                    updated_account = dict(target_account)
                updated_account["positions"] = merged_positions
                portfolio["accounts"][detected_account] = updated_account
                portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                # Record change history
                delta = compute_delta(previous_snapshot.get("positions", []), parsed_positions)
                account_summary = {
                    "total_assets": updated_account.get("total_assets"),
                    "total_positions": len(merged_positions),
                }
                history_file = user_history_file(user)
                record_change(
                    history_file,
                    change_type="ocr_import",
                    account=detected_account,
                    delta=delta,
                    summary=account_summary,
                    previous_snapshot=previous_snapshot,
                )

                save_portfolio(user, portfolio)
                reload_portfolio()
                for key in ("ocr_import_parsed", "ocr_import_summary", "ocr_import_positions", "ocr_editor"):
                    st.session_state.pop(key, None)
                st.success(f"已更新 {detected_account} 持仓，共 {len(merged_positions)} 条。变更已记录到历史。")
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
            save_portfolio(user, portfolio)
            reload_portfolio()
            st.success(f"已添加 {manual_name} 到 {manual_account}，共 {len(merged)} 条持仓。")
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
