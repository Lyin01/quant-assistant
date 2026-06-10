# Phase B Import Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portfolio import safer by detecting the target account clearly, showing validation issues before write, and exposing rollback from the import workflow.

**Architecture:** Add `import_review.py` as a pure validation layer between parsed positions and Streamlit write actions. Streamlit remains responsible for rendering controls and calling existing `merge_positions`, `record_change`, and `rollback` functions.

**Tech Stack:** Python, Streamlit, pandas, pytest

---

### Task 1: Import Review Helper

**Files:**
- Create: `src/quant_assistant/import_review.py`
- Create: `tests/test_import_review.py`

- [ ] Test account detection from summary, preset, and shares.
- [ ] Test issue generation for empty imports, missing values, stock-specific missing fields, and new imported tags.
- [ ] Implement helpers after red tests.

### Task 2: Streamlit Import Page Wiring

**Files:**
- Modify: `app.py`

- [ ] Show validation tables before CSV and OCR/text confirmation buttons.
- [ ] Disable confirmation when validation contains blocking errors.
- [ ] Add a target-account override for OCR/text imports.
- [ ] Add an import-page rollback expander using the existing history module.

### Task 3: Verification

**Files:**
- Read only.

- [ ] Run `python -m pytest`.
- [ ] Run CLI snapshot smoke test.
- [ ] Confirm Streamlit responds on localhost.
- [ ] Run `git diff --check`.
