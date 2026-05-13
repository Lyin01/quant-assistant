# Quant Assistant

本项目是本地半自动量化复盘助手。它不会自动真实下单，只负责：

- 拉取行情
- 支持 AkShare / 东方财富行情源
- 读取持仓和资金配置
- 按配置里的交易纪律生成买卖建议
- 保存复盘日志

## 快速运行

PowerShell:

```powershell
cd "E:\PROJECT FROM CODEX"
.\run_cli.ps1
```

如果要开本地网页：

```powershell
cd "E:\PROJECT FROM CODEX"
pip install -r requirements.txt
.\run_app.ps1
```

## 文件说明

- `config.json`：策略参数、现金分配、行情代码。
- `portfolio.json`：当前持仓快照。
- `src/quant_assistant/strategy.py`：核心规则。
- `src/quant_assistant/data_provider.py`：AkShare / 东方财富行情抓取。
- `src/quant_assistant/cli.py`：命令行入口。
- `app.py`：Streamlit 本地页面。
- `data/journal.csv`：运行后自动生成的复盘日志。

## 当前默认纪律

- AI 小仓：长期定投，不按短线卖。
- AI 大仓、电网、机器人、半导体：进攻仓，涨多止盈，回调企稳再买。
- 中证500 / A500：底仓，优先用现金回补。
- 军工：不补仓，反弹后降低暴露。
- 现金：保留底线现金，不满仓。

## 行情口径

默认配置为：

```json
"name": "auto",
"use_live_proxy_for_decisions": false
```

`auto` 会先尝试 AkShare，失败后回退到东方财富直连。

原因：基金页面的“关联板块”与可拉取 ETF 代理行情可能不同步。默认用 `portfolio.json` 里的 `last_daily_pct` 作为交易决策口径，实时行情只用于看盘参考。确认代理代码完全匹配后，可以把 `use_live_proxy_for_decisions` 改为 `true`。

## 风险边界

这不是自动交易系统，也不是收益承诺。输出是本地规则建议，真实下单仍需人工确认。
