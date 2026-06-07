# Portfolio Snapshot Audit - 2026-06-05

This report compares the archival 2026-05-15 screenshot data recorded in `CLAUDE.md` with the current root `portfolio.json` snapshot.

Current snapshot:

```text
portfolio.json as_of: 2026-05-19 12:53
```

Conclusion: do not overwrite the current `portfolio.json` with the 2026-05-15 screenshots. The current snapshot is later, and the stock account contains positions that were not present in the 2026-05-15 screenshot notes.

## Account Summary

| Account | Field | 2026-05-15 screenshot | Current portfolio | Delta |
| --- | ---: | ---: | ---: | ---: |
| fund | total_assets | 18,118.73 | 17,845.18 | -273.55 |
| fund | today_pnl | -228.25 | -78.30 | +149.95 |
| stock | total_assets | 6,245.08 | 9,292.53 | +3,047.45 |
| stock | today_pnl | -40.00 | -260.10 | -220.10 |
| stock | holding_pnl | -15.22 | -567.77 | -552.55 |
| stock | market_value | 4,600.80 | 9,270.30 | +4,669.50 |
| stock | available_cash | 1,644.28 | 22.23 | -1,622.05 |

## Position Coverage

Fund account:

- Added in current snapshot: none.
- Missing from current snapshot: none.
- All nine 2026-05-15 fund positions still exist in the current snapshot.

Stock account:

- Added in current snapshot: `通宇通讯`, `机器人`.
- Missing from current snapshot: none.
- The four 2026-05-15 stock positions still exist in the current snapshot.

## Fund Position Deltas

Delta means current portfolio minus 2026-05-15 screenshot.

| Name | Market value delta | Holding pnl delta | Holding pnl pct delta | Daily pct delta |
| --- | ---: | ---: | ---: | ---: |
| 华宝纳斯达克精选 | -63.33 | -63.33 | -2.20 | -1.51 |
| 博时标普500ETF联接 | -1.25 | -1.25 | -1.25 | -0.84 |
| 大成纳斯达克100 | -18.52 | -18.52 | -0.93 | -1.18 |
| 天弘中证人工智能大仓 | -26.74 | -26.74 | -1.84 | +1.32 |
| 天弘中证人工智能定投小仓 | -7.17 | -7.17 | -1.79 | +1.32 |
| 天弘中证电网设备 | -42.96 | -42.96 | -1.47 | +3.28 |
| 广发中证军工ETF联接 | -39.49 | -39.49 | -2.68 | +1.16 |
| 易方达中证500 | -72.50 | -72.50 | -1.28 | +1.22 |
| 易方达稳健收益 | -1.61 | -1.61 | -0.40 | +0.10 |

## Stock Position Deltas

Delta means current portfolio minus 2026-05-15 screenshot.

| Name | Market value delta | Price delta | Holding pnl delta | Holding pnl pct delta |
| --- | ---: | ---: | ---: | ---: |
| 创新药 | -5.10 | -0.02 | -5.10 | -2.07 |
| 半导体 | +3.80 | +0.04 | +3.80 | +1.84 |
| 沃尔核材 | -110.00 | -1.10 | -110.00 | -4.78 |
| 纳指大成 | -39.60 | -0.04 | -39.60 | -2.55 |

New current-only stock positions:

| Name | Tag | Shares | Market value | Holding pnl pct |
| --- | --- | ---: | ---: | ---: |
| 通宇通讯 | imported | 100 | 4,812.00 | -7.85 |
| 机器人 | robot | 300 | 357.60 | +15.58 |

## Consistency Checks

- The 2026-05-15 fund screenshot rows sum exactly to the recorded fund account total: 18,118.73.
- Current fund position rows sum to 17,845.16, which differs from current `total_assets` by only 0.02, likely rounding.
- The current stock rows sum exactly to current `market_value`: 9,270.30.
- The 2026-05-15 stock screenshot rows sum to 4,251.60, while the recorded stock `总市值` is 4,600.80. The 349.20 gap means stock row-level deltas should be treated as a position comparison, not a full account reconciliation.

## Actionable Notes

- Keep `portfolio.json` as the 2026-05-19 snapshot unless the user asks to restore an older account state.
- If updating strategies, remember that `通宇通讯` and `沃尔核材` are stored as `imported` but currently route through the generic `short_term` stock rule. Dedicated rules would be a product decision, not an uncovered-strategy bug fix.
- Do not infer aggressive trading rules from this audit. It only proves snapshot differences.
