# Code Health Audit - 2026-06-05

This report records small maintainability checks made while preparing the final handoff.

## Findings Resolved

### Duplicate health-warning helper

File: `src/quant_assistant/strategy.py`

`_prepend_health_warning` was defined twice with identical logic. Python used the second definition at runtime, so behavior was not broken, but duplicate definitions make future edits risky because a maintainer may patch one copy and not the other.

The strategy layer now also uses finite-number coercion for tag fallback, cash deployment, price/profit inputs, market-value checks, and quote fallbacks. Regression tests in `tests/test_strategy.py` cover malformed numeric inputs without changing the intended recommendation thresholds.

Resolution: removed the duplicate second definition and kept the first implementation used by `generate_recommendations`.

Expected behavior remains unchanged:

- Health warnings are still prepended when a provider has at least 5 requests and success rate below 80%.
- Trading-day notices still run after health warnings.
- Fund and stock recommendations are generated in the same order as before.

### Daily report cleanup

File: `src/quant_assistant/daily_report.py`

The module imported `AutoProvider`, `collect_secids`, and `generate_recommendations` even though report generation now delegates through `run_pipeline`. These imports were removed to keep the module boundary clear.

Regression tests were added in `tests/test_daily_report.py` to pin the intended tomorrow-plan behavior:

- concentration and cash-stress findings should not create a "补充策略规则" task;
- a "补充策略规则" task is added only when the risk findings explicitly contain "无策略覆盖".

### Duplicate-definition regression guard

File: `tests/test_code_health.py`

An AST-based regression test now checks `app.py` and `src/quant_assistant/*.py` for duplicate top-level functions, async functions, and classes. This keeps the duplicate-helper cleanup above from silently regressing without importing Streamlit or touching network-dependent modules.

The same test module also checks `scripts/verify_quant_assistant.ps1` as a read-only verification entrypoint. It requires the expected syntax, pytest, CLI no-live, CLI no-write hash guard, and diff-check commands, and rejects obvious mutation commands such as `git add`, `git commit`, `--save-log`, file writes, deletes, and `save_portfolio`.

It also runs `git check-ignore` against representative report paths so generated reports remain ignored while final-day `*_audit_2026-06-05.md` handoff files remain trackable.

The primary runbook docs are also checked so `CLAUDE.md` and `README.md` continue to prefer the verified Windows `py` launcher commands and `scripts/verify_quant_assistant.ps1` entrypoint.

The suggested selective `git add` block in `reports/change_set_audit_2026-06-05.md` is checked as well. It must include the intentional final-day files and avoid broad or unrelated paths such as `portfolio.json`, `config.json`, `data/journal.csv`, IDM artifacts, image experiments, and duplicate worktrees.

### OCR import state cleanup

File: `app.py`

The OCR import page previously repeated the same `st.session_state.pop(...)` loops around screenshot OCR, text parsing, and confirmed writes. These now route through shared OCR state key tuples and `_clear_session_state(...)`, reducing the chance that a future UX state key is cleared in one path but not another.

### OCR import numeric hardening

Files: `src/quant_assistant/importer.py`, `src/quant_assistant/import_review.py`

Imported rows, OCR-derived positions, position merging, account splitting, account summary recalculation, account detection, and import review now treat malformed numeric values as missing instead of raising or overwriting existing good values. Regression tests in `tests/test_importer.py` and `tests/test_import_review.py` cover those boundaries.

### Schema numeric validation

File: `src/quant_assistant/schema.py`

Schema validation now rejects non-finite config cash-plan values and malformed portfolio account or position numeric fields before the data reaches strategy, analytics, or CLI code. Regression tests in `tests/test_schema.py` cover config, account-level, and position-level numeric validation.

### LLM review prompt hardening

File: `src/quant_assistant/llm_advisor.py`

LLM context and prompt assembly now coerce malformed numeric values to safe display defaults and treat strategy-tag resolution failures as uncovered positions. Regression tests in `tests/test_llm_advisor.py` cover bad account and holding numbers in both context and prompt paths.

### Multi-agent risk hardening

File: `src/quant_assistant/multi_agent.py`

Data, analysis, decision, and risk agent helpers now skip malformed account/position shapes and coerce malformed numeric values before cash, concentration, uncovered-position, and drawdown summaries. Regression tests in `tests/test_multi_agent.py` cover those paths.

### History persistence guard

File: `src/quant_assistant/history.py`

History records now create their parent directories before appending JSONL records, matching the journal writer's behavior and making nested history paths safe. The history helpers also accept both `Path` and string paths. Regression tests in `tests/test_history.py` verify the behavior with temporary nested and string paths.

### User data directory hardening

File: `src/quant_assistant/user_data.py`

Per-user data directories now sanitize both the auth provider and user identifier before composing the directory name. Safe email characters are preserved, while path-like fragments are normalized away. Regression tests in `tests/test_user_data.py` cover both cases.

### Config save path guard

File: `src/quant_assistant/config.py`

Config JSON saves now create missing parent directories before writing, matching the persistence behavior added for journal and history files. Regression tests in `tests/test_config.py` also keep the `Quant assistant/` fallback load path pinned.

### Data source health persistence guard

File: `src/quant_assistant/data_source_health.py`

Health JSONL records now create missing parent directories before writing. `read_health(days <= 0)` also returns an empty list explicitly. Regression tests in `tests/test_data_source_health.py` cover both boundaries.

### Cache filename hardening

File: `src/quant_assistant/disk_cache.py`

History and generic cache helpers now sanitize cache keys before deriving local file names, keeping path-like fragments inside the intended cache directories. Regression tests in `tests/test_disk_cache.py` cover sanitized history cache paths, generic cache save/load behavior, and ignored `None` generic-cache writes.

### Analytics history and distribution hardening

File: `src/quant_assistant/analytics_panel.py`

Portfolio history analysis now accepts both `Path` and string inputs and skips malformed-but-valid JSONL records whose shape, timestamp, or asset value cannot be used for charting. Regression tests in `tests/test_analytics_panel.py` cover those cases.

The analytics metrics also avoid non-finite results from zero or invalid asset values. Monthly returns skip months whose starting asset value is non-positive, and risk metrics require at least two positive asset-value observations before computing drawdown, volatility, or Sharpe ratio.

Return curves, monthly returns, and risk metrics now share a small input-normalization path that coerces timestamps and asset values, drops unusable rows, and sorts by timestamp before calculating metrics.

Asset distribution generation now skips malformed account and position shapes and coerces invalid, missing, or NaN market values to zero before building the display DataFrame.

## Related Cleanups Already Recorded

- Snapshot comparison: `reports/portfolio_snapshot_audit_2026-06-05.md`
- Strategy coverage audit: `reports/strategy_coverage_audit_2026-06-05.md`
- Final handoff: `LAST_DAY_HANDOFF_2026-06-05.md`

## Verification

Run from repository root:

```powershell
py -m pytest
```

The latest verification after this cleanup should remain green.

Latest observed result:

```text
218 passed
```
