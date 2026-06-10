# Phase A Trust And Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily overview clearer and more trustworthy without changing holdings, Google login, or trading rules.

**Architecture:** Add a small pure helper module for recommendation presentation and strategy coverage diagnostics, then wire it into the Streamlit overview. Keep behavior changes covered by unit tests and keep documentation/config updates narrow.

**Tech Stack:** Python, Streamlit, pandas, pytest

---

### Task 1: Recommendation Presentation Helpers

**Files:**
- Create: `src/quant_assistant/recommendation_view.py`
- Create: `tests/test_recommendation_view.py`

- [ ] Add tests for splitting actionable recommendations from HOLD items.
- [ ] Add tests for adding a `数据来源` column to recommendation tables.
- [ ] Implement helper functions only after the tests fail.

### Task 2: Strategy Coverage Diagnostics

**Files:**
- Modify: `src/quant_assistant/recommendation_view.py`
- Modify: `tests/test_recommendation_view.py`

- [ ] Add tests for imported holdings, missing market proxies, and unknown market proxies.
- [ ] Implement `strategy_coverage_issues(config, portfolio)`.

### Task 3: Overview Wiring

**Files:**
- Modify: `app.py`

- [ ] Replace the flat recommendation display with separate actionable and watchlist sections.
- [ ] Add the strategy coverage expander near the daily recommendation area.
- [ ] Preserve existing CSV download behavior for actionable rows.

### Task 4: CLI Snapshot Status

**Files:**
- Modify: `src/quant_assistant/cli.py`

- [ ] Make `--no-live` print an explicit snapshot-mode status line instead of the live-decision status.

### Task 5: Project Documentation And Test Config

**Files:**
- Modify: `README.md`
- Modify: `pytest.ini`

- [ ] Replace the stale project README with Quant Assistant run/test/deploy notes.
- [ ] Add pytest basetemp config so `python -m pytest` avoids the locked Windows temp path.

### Task 6: Verification

**Files:**
- Read only.

- [ ] Run `python -m pytest`.
- [ ] Run the no-live CLI smoke command.
- [ ] Inspect `git diff --check`.
