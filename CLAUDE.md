# Claude Code Handoff - Quant Assistant

You are taking over the Quant Assistant project for LY. Treat this file as the project handoff and operating context.

## Prime Directive

Build and maintain a local/semi-cloud quant review assistant for the user's own portfolio. The app must generate analysis and suggested buy/sell lists only. It must never place real orders, store brokerage credentials, or imply guaranteed investment outcomes.

Communication with the user should be direct, concrete, and in Chinese unless they ask otherwise. The user wants actionable output, not long theory.

## Repository And Deployment

- Main repo path: `E:\project from reasonix\Quant assistant`
- GitHub remote: `https://github.com/Lyin01/quant-assistant.git`
- Branch: `main`
- Streamlit Cloud URL: `https://lyuiqsvrtmnzxhpxf5ulyo.streamlit.app`
- Streamlit entrypoint: `app.py`
- Pushing `main` triggers Streamlit Cloud redeploy.

Do not treat sibling scratch copies such as `portfolio-app/` outside this repo as the deploy root unless the user explicitly redirects you. The deployed repo root is `E:\project from reasonix\Quant assistant`.

Current Git notes at handoff:

- `HEAD` / `origin/main`: `368095d Improve screenshot holding import parser`
- Recent commits:
  - `368095d Improve screenshot holding import parser`
  - `c97636b Make dashboard recommendations use live quotes`
  - `931ce84 Add OCR text position import`
  - `df4605f Add resilient market data fallbacks`
  - `4fec083 Avoid eager Streamlit data loading`
- Sibling scratch directories such as `.claude/`, `docs/`, `flow/`, and `data/` now live outside this repo after the root migration.
- Do not stage or revert files outside this repo unless the user explicitly requests it.

## Runbook

```powershell
cd "E:\project from reasonix\Quant assistant"
python -m pip install -r requirements.txt
python -m pytest
streamlit run app.py
```

If `python` points to the wrong interpreter on Windows, use `py -m pytest` and `py -m streamlit run app.py`.

Deployment:

```powershell
cd "E:\project from reasonix\Quant assistant"
git status --short
git add app.py src tests config.json portfolio.json requirements.txt CLAUDE.md DEPLOY.md
git commit -m "Describe exact change"
git push origin main
```

Be selective with `git add`. This workspace contains unrelated files.

## Product State

The app is a Streamlit application with these pages:

- `总览`
  - Shows fund assets, stock assets, stock available cash, planned cash.
  - Fetches live quotes with `cached_quotes`.
  - Displays `行情快照`.
  - Generates `今日买卖清单（基于实时行情）` when quotes exist, otherwise falls back to `portfolio.json` snapshot values.
- `历史 K 线`
  - Loads historical K lines.
  - Adds MA20/MA60 indicators.
- `信号 / ETF 排行`
  - Computes moving-average/drawdown signal.
  - Loads ETF gain/loss ranking.
- `回测`
  - MA trend backtest.
- `导入持仓`
  - CSV/Excel import with column mapping.
  - Screenshot preview.
  - OCR text paste parser for stock/fund screenshots.
  - Manual fallback input.

Important: the current screenshot feature does not perform real image OCR. It previews the uploaded image and parses text pasted by the user after phone/WeChat OCR. If the user expects direct image recognition, that is a pending feature.

## Core Files

- `app.py`
  - Streamlit UI and page routing.
  - Quote cache TTL: 600 seconds.
  - History/ETF cache TTL: 900 seconds.
  - Main user-visible behavior lives here.
- `config.json`
  - Cash plan, decision thresholds, quote proxy secids.
  - `market_provider.use_live_proxy_for_decisions` is currently `true`.
- `portfolio.json`
  - User portfolio snapshot.
  - May be stale relative to latest screenshots; see "Latest User Data".
- `requirements.txt`
  - `streamlit`, `akshare`, `pandas`, `plotly`, `openpyxl`.
- `src\quant_assistant\strategy.py`
  - Generates recommendations.
  - Uses live quote pct/price when available and configured.
  - Falls back to `last_daily_pct`, `price`, `holding_pnl_pct` from `portfolio.json`.
- `src\quant_assistant\data_provider.py`
  - Quote provider layer.
  - `AutoProvider` fallback order: AkShare, EastMoney, Tencent.
- `src\quant_assistant\market_data.py`
  - Historical K-line and ETF ranking helpers.
- `src\quant_assistant\analytics.py`
  - Indicators, signals, backtest, action-list formatting.
- `src\quant_assistant\importer.py`
  - CSV/Excel normalization.
  - OCR text parser: `parse_ocr_positions`, `parse_ocr_summary`.
- `tests\test_strategy.py`
  - Strategy, live-quote behavior, importer parsing tests.

## Current Decision Rules

These rules are encoded in `config.json` and `strategy.py`.

- Keep cash reserve. `minimum_cash_reserve` is `5000`.
- Planned total "子弹" is `13000`.
- Wide-index / 中证500:
  - Deploy only when cash is above `9000`.
  - Buy when wide-index reference daily pct is `<= 0.5`.
  - Strong buy when `<= -1.0`.
  - Normal buy amount `1000`, strong buy amount `1500`.
- AI small DCA:
  - Long-term定投仓.
  - Do not sell based on short-term volatility.
- AI large tactical:
  - Sell `500` when daily pct `>= 1.5` and holding profit pct `>= 12`.
  - Buy `500` when daily pct `<= -3.0` and cash allows.
- 电网:
  - Sell `500` when daily pct `>= 1.5` and holding profit pct `>= 12`.
- 军工:
  - Do not buy.
  - Sell `500` after rebound to holding profit pct `>= 0` and daily pct non-negative.
- 半导体:
  - Limit buy at or below `2.000`.
  - Buy 100 shares.
  - Do not chase above `2.030`.
  - Max position 300 shares.
- 机器人:
  - Sell 100 shares when holding profit pct `>= 12`.
  - Buy 100 shares only in pullback range `1.08` to `1.10`.

## Latest User Data From 2026-05-15 Screenshots

The user uploaded fresher screenshots after the current `portfolio.json` snapshot. If you are updating the portfolio, use this as the canonical latest visible data.

Stock account screenshot, 国信证券:

```text
总资产: 6245.08
今日盈亏: -40.00
持仓盈亏: -15.22
总市值: 4600.80
可用: 1644.28
沃尔核材 | 2249.00 | 100 | 100 | 22.490 | 23.000 | -51.02 | -2.22%
纳指大成 | 1559.70 | 900 | 900 | 1.733 | 1.725 | +7.60 | +0.49%
创新药 | 239.40 | 300 | 300 | 0.798 | 0.825 | -8.00 | -3.23%
半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%
```

Fund account screenshot, 支付宝:

```text
账户资产: 18118.73
场内穿透: -228.25
博时标普500ETF联接 | 109.18 | +0.77% | +9.18 | +9.18%
华宝纳斯达克精选 | 3145.75 | +0.97% | +269.53 | +9.37%
易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%
天弘中证人工智能定投小仓 | 459.98 | -2.26% | +59.98 | +14.99%
大成纳斯达克100 | 2046.11 | +0.73% | +46.11 | +2.31%
易方达稳健收益 | 399.69 | -0.14% | -0.31 | -0.08%
天弘中证人工智能大仓 | 1717.05 | -2.26% | +264.36 | +18.20%
广发中证军工ETF联接 | 1375.92 | -2.35% | -94.17 | -6.41%
天弘中证电网设备 | 3270.40 | -3.24% | +363.23 | +12.49%
```

Note that `portfolio.json` at handoff still shows `as_of: 2026-05-13 10:55` and older values. Updating it from the latest screenshots is a likely next task.

## Current Screenshot Import Parser Behavior

Recommended stock text format:

```text
总资产: 6245.08
今日盈亏: -40.00
持仓盈亏: -15.22
总市值: 4600.80
可用: 1644.28
半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%
```

Stock row mapping:

- name
- market value
- shares
- sellable shares
- price
- cost
- holding pnl
- holding pnl pct

Recommended fund text format:

```text
账户资产: 18118.73
场内穿透: -228.25
易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%
```

Fund row mapping:

- name
- market value
- last daily pct
- holding pnl
- holding pnl pct

The parser intentionally avoids treating digits embedded in names like `中证500` as numeric columns.

## Known Issues / Next Best Tasks

1. Add real image OCR only if you can keep Streamlit Cloud stable.
   - Current implementation is text-paste OCR parsing, not image OCR.
   - Heavy OCR packages may break Streamlit Cloud cold start or dependency install.
   - A pragmatic path is optional OCR behind a dependency guard, while preserving paste-text fallback.
2. Update `portfolio.json` from the 2026-05-15 latest screenshots.
   - Do not overwrite tags/rules casually.
   - Add new stock positions such as `沃尔核材` and `纳指大成` with reasonable tags, or mark as `imported` if no strategy rule exists.
3. Improve "导入持仓" UX.
   - Make it explicit whether the app is doing image OCR or only parsing pasted OCR text.
   - Keep screenshot preview small.
   - Ensure form submit visibly changes output.
4. Verify live quote display on Streamlit Cloud.
   - AkShare can fail depending on network/provider behavior.
   - Auto fallback currently tries AkShare, EastMoney, Tencent.
   - If live data fails, inspect `行情源状态`.
5. Expand strategy coverage for newly visible holdings.
   - `沃尔核材`, `纳指大成`, `创新药`, overseas funds currently do not all have dedicated rules.
   - Avoid inventing aggressive trading rules without the user's consent.

## Testing Expectations

Before telling the user something is fixed:

```powershell
cd "E:\project from reasonix\Quant assistant"
python -m pytest
```

If changing Streamlit UI, also run locally:

```powershell
streamlit run app.py
```

If pushing, check the deployed app after Streamlit Cloud redeploys.

## User Preferences

- The user wants clear "今天怎么操作" style output: action first, then amount/shares, then short reason.
- User often thinks in "子弹" / available cash.
- The user dislikes static or fake-real-time analysis. If using fallback data, say so visibly.
- Keep investment advice bounded as a rule-based assistant. Do not overpromise.

## Safety Boundaries

- Never ask for or store brokerage passwords, trading passwords, ID numbers, or bank data.
- Never connect a real trading API unless the user explicitly asks and understands the risks.
- Never auto-submit orders.
- Keep all generated project files under `E:\project from reasonix\Quant assistant` unless the user explicitly asks otherwise.
