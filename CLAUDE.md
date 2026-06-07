# Claude Code Handoff - Quant Assistant

You are taking over the Quant Assistant project for LY. Treat this file as the project handoff and operating context.

## Prime Directive

Build and maintain a local/semi-cloud quant review assistant for the user's own portfolio. The app must generate analysis and suggested buy/sell lists only. It must never place real orders, store brokerage credentials, or imply guaranteed investment outcomes.

Communication with the user should be direct, concrete, and in Chinese unless they ask otherwise. The user wants actionable output, not long theory.

## Repository And Deployment

- Main repo path: `E:\PROJECT FROM CODEX`
- GitHub remote: `https://github.com/Lyin01/quant-assistant.git`
- Branch: `main`
- Streamlit Cloud URL: `https://lyuiqsvrtmnzxhpxf5ulyo.streamlit.app`
- Streamlit entrypoint: `app.py`
- Pushing `main` triggers Streamlit Cloud redeploy.

Do not treat `E:\PROJECT FROM CODEX\portfolio-app` as the deploy root unless the user explicitly redirects you. It is a duplicate/older copy. The deployed repo root is `E:\PROJECT FROM CODEX`.

Current Git notes at handoff:

- `HEAD` / `origin/main`: `368095d Improve screenshot holding import parser`
- Recent commits:
  - `368095d Improve screenshot holding import parser`
  - `c97636b Make dashboard recommendations use live quotes`
  - `931ce84 Add OCR text position import`
  - `df4605f Add resilient market data fallbacks`
  - `4fec083 Avoid eager Streamlit data loading`
- Known unrelated dirty/untracked items at handoff:
  - modified `README.md`
  - untracked `agent-trials/`, `codex-claude-install-tutorial-v3.mp4`, `codex-clawbot-bridge/`, `depcheck-grade-fixture*/`, `portfolio-app/`, `video-projects/`
- Do not stage or revert unrelated files unless the user explicitly requests it.

## Runbook

```powershell
cd "E:\PROJECT FROM CODEX"
py -m pip install -r requirements.txt
.\scripts\verify_quant_assistant.ps1
py -m streamlit run app.py
```

On this Windows workspace, prefer the `py` launcher. The bare `python` command may point to the Codex/Hermes environment, which can lack project dependencies.

Deployment:

```powershell
cd "E:\PROJECT FROM CODEX"
git status --short
# Add only the files intentionally changed for this task.
# For the 2026-06-05 handoff set, see reports/change_set_audit_2026-06-05.md.
git commit -m "Describe exact change"
git push origin main
```

Be selective with `git add`. This workspace contains unrelated files and user data snapshots. For the 2026-06-05 final-day change set, use `reports/change_set_audit_2026-06-05.md` instead of broad pathspecs such as `src`, `tests`, or `portfolio.json`.

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
  - Uploaded screenshot OCR through RapidOCR when dependencies are available.
  - OCR text paste parser for stock/fund screenshots.
  - Manual fallback input.

Important: screenshot import now has two paths. It can run RapidOCR on uploaded JPG/PNG screenshots when the OCR dependencies are installed and Python is below 3.13, and it can also parse pasted phone/WeChat OCR text. Keep the paste-text fallback visible because image OCR can still fail or be unavailable in deployment.

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
  - Current root snapshot observed on 2026-06-05 shows `as_of: 2026-05-19 12:53`, which is later than the 2026-05-15 screenshot notes below. Do not overwrite it with older screenshot data unless the user explicitly confirms that rollback.
- `requirements.txt`
  - `streamlit`, `akshare`, `pandas`, `plotly`, `openpyxl`.
- `src\quant_assistant\strategy.py`
  - Generates recommendations.
  - Uses live quote pct/price when available and configured.
  - Falls back to `last_daily_pct`, `price`, `holding_pnl_pct` from `portfolio.json`.
- `src\quant_assistant\data_provider.py`
  - Quote provider layer.
  - `AutoProvider` default order: EastMoney and Tencent. AkShare quote fetching is opt-in with `QA_ENABLE_AKSHARE_QUOTES=1`.
- `src\quant_assistant\market_data.py`
  - Historical K-line and ETF ranking helpers.
- `src\quant_assistant\etf_universe.py`
  - Shared fallback ETF universe for ranking and scanner when live list APIs fail.
- `src\quant_assistant\macro_dashboard.py`
  - Macro dashboard uses lightweight FRED / Yahoo fallback by default.
  - AkShare macro data is opt-in with `QA_ENABLE_AKSHARE_MACRO=1`.
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

Historical handoff note: these screenshots were fresher than the portfolio snapshot at the time they were recorded. In the current worktree observed on 2026-06-05, root `portfolio.json` is already `as_of: 2026-05-19 12:53`, so the 2026-05-15 screenshots should be treated as archival reference unless the user explicitly asks to restore or compare against them.

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

Earlier handoff note: at that time `portfolio.json` showed `as_of: 2026-05-13 10:55` and older values. This is no longer true in the current worktree; do not use this note as a reason to overwrite the 2026-05-19 snapshot.

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

1. Keep screenshot OCR deploy-stable.
   - Real image OCR is wired through RapidOCR, but it depends on runtime packages and Python version support.
   - Preserve the paste-text fallback and clear failure messages.
   - Do not add heavier OCR dependencies unless Streamlit Cloud install and cold start are verified.
2. Do not overwrite `portfolio.json` with the 2026-05-15 screenshot data without confirmation.
   - Current root snapshot observed on 2026-06-05 is `as_of: 2026-05-19 12:53`.
   - Snapshot comparison is documented in `reports/portfolio_snapshot_audit_2026-06-05.md`.
3. Improve "导入持仓" UX.
   - The page now labels the image OCR and pasted-text paths more clearly.
   - Uploaded screenshots now have a small collapsed preview before OCR.
   - OCR import writes now persist a post-rerun success notice that points users to the change history.
4. Verify live quote display on Streamlit Cloud.
   - AkShare can fail depending on network/provider behavior and is disabled by default in `auto`.
   - Auto fallback currently uses EastMoney and Tencent; enable AkShare only with explicit `QA_ENABLE_*` environment variables.
   - If live data fails, inspect `行情源状态`.
   - Macro dashboard should still show FRED / Yahoo fallback values when AkShare macro data is disabled.
5. Strategy coverage is currently clean, but some coverage is generic.
   - Current strategy coverage audit is documented in `reports/strategy_coverage_audit_2026-06-05.md`.
   - `沃尔核材` and `通宇通讯` are stored as `imported` but route through the generic `short_term` stock rule.
   - Avoid inventing dedicated aggressive trading rules without the user's consent.

## Testing Expectations

Before telling the user something is fixed:

```powershell
cd "E:\PROJECT FROM CODEX"
.\scripts\verify_quant_assistant.ps1
```

If changing Streamlit UI, also run locally:

```powershell
py -m streamlit run app.py
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
- Keep all generated project files under `E:\PROJECT FROM CODEX` unless the user explicitly asks otherwise.
