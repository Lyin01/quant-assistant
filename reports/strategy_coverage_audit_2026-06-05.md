# Strategy Coverage Audit - 2026-06-05

This report records the current strategy coverage state for `portfolio.json` as observed after fixing the `core_ai_dca` coverage-check false positive.

Current snapshot:

```text
portfolio.json as_of: 2026-05-19 12:53
strategy_coverage_issues: 0
```

## Key Clarifications

- `imported` is a stored tag, not always the effective strategy tag.
- Stock-account `imported` positions with shares and price/cost data are routed through the built-in `short_term` rule by `position_strategy_tag`.
- `core_ai_dca` is a built-in hold-only strategy. It does not need a threshold entry in `config.json` to be considered covered.
- The generated `reports/report_2026-05-19.md` is historical and still contains an older "无策略覆盖: 沃尔核材, 通宇通讯" finding. Current code no longer reports those two as uncovered because they route to `short_term`.

## Fund Positions

| Name | Stored tag | Effective tag | Live quote required | Current action |
| --- | --- | --- | --- | --- |
| 易方达中证500 | wide_index | wide_index | yes | HOLD |
| 天弘中证人工智能定投小仓 | core_ai_dca | core_ai_dca | no | HOLD |
| 大成纳斯达克100 | overseas | overseas | yes | HOLD |
| 易方达稳健收益 | defensive | defensive | no | HOLD |
| 博时标普500ETF联接 | overseas | overseas | yes | HOLD |
| 天弘中证人工智能大仓 | tactical_ai | tactical_ai | yes | HOLD |
| 广发中证军工ETF联接 | military | military | yes | HOLD |
| 天弘中证电网设备 | power_grid | power_grid | yes | HOLD |
| 华宝纳斯达克精选 | overseas | overseas | yes | HOLD |

## Stock Positions

| Name | Stored tag | Effective tag | Live quote required | Current action |
| --- | --- | --- | --- | --- |
| 沃尔核材 | imported | short_term | no | HOLD |
| 通宇通讯 | imported | short_term | no | HOLD |
| 纳指大成 | overseas | overseas | no | HOLD |
| 创新药 | healthcare | healthcare | no | HOLD |
| 半导体 | semiconductor | semiconductor | yes | HOLD |
| 机器人 | robot | robot | yes | SELL |

## Current Risk Agent Findings

- 现金紧张: 股票可用仅 22.23 元
- 高度集中: 通宇通讯 占股票市值 51.9%

## Actionable Notes

- Do not treat `沃尔核材` and `通宇通讯` as completely uncovered in current code. They are handled by the generic short-term stock rule.
- Dedicated rules for `沃尔核材` or `通宇通讯` may still be useful, but they should be a product decision rather than a bug fix.
- The next high-value improvement is likely a clearer UI distinction between stored tag and effective strategy tag, especially for `imported -> short_term`.
