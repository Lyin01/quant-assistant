from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.config import load_json
from quant_assistant.data_provider import EastMoneyProvider, collect_secids
from quant_assistant.strategy import generate_recommendations


st.set_page_config(page_title="Quant Assistant", layout="wide")
st.title("Quant Assistant")
st.caption("本地半自动复盘助手。只生成建议，不自动真实下单。")

config = load_json(ROOT / "config.json")
portfolio = load_json(ROOT / "portfolio.json")

provider = EastMoneyProvider(timeout=config["market_provider"]["timeout_seconds"])
secids = collect_secids(config, portfolio)
quotes = provider.get_quotes(secids)

recs = generate_recommendations(config, portfolio, quotes)

fund = portfolio["accounts"]["fund"]
stock = portfolio["accounts"]["stock"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("基金资产", f'{fund["total_assets"]:,.2f}', f'{fund["today_pnl"]:,.2f}')
col2.metric("股票资产", f'{stock["total_assets"]:,.2f}', f'{stock["today_pnl"]:,.2f}')
col3.metric("股票可用", f'{stock["available_cash"]:,.2f}')
col4.metric("计划总子弹", f'{config["cash_plan"]["available_cash_total"]:,.0f}')

st.subheader("今日建议")
if not recs:
    st.info("当前没有触发明确操作。")
else:
    for rec in recs:
        st.write(f'**{rec["action"]}** `{rec["instrument"]}` `{rec["amount"]}`')
        st.caption(rec["reason"])

st.subheader("行情快照")
if quotes:
    st.dataframe(
        [
            {
                "名称": quote.name,
                "代码": quote.code,
                "价格": quote.price,
                "涨跌幅%": quote.pct,
                "时间": quote.time_text,
            }
            for quote in quotes.values()
        ],
        use_container_width=True,
    )
else:
    st.warning("未获取到实时行情，将使用 portfolio.json 里的 last_daily_pct。")
