# Phase C Structure And Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce maintenance risk by adding lightweight data validation, extracting pure import helpers from `app.py`, and documenting repo hygiene without moving unrelated user files.

**Architecture:** Add a pure `schema.py` validation layer for `config.json` and `portfolio.json`. Reuse the existing import review module for pure import helper logic. Wire validation into Streamlit and CLI before the app indexes nested data.

**Tech Stack:** Python, Streamlit, pandas, pytest

---

### Task 1: Lightweight Schema Validation

**Files:**
- Create: `src/quant_assistant/schema.py`
- Create: `tests/test_schema.py`

- [ ] Test valid config and portfolio produce no blocking errors.
- [ ] Test missing required config sections produce errors.
- [ ] Test missing account sections and malformed positions produce errors.
- [ ] Implement validation helpers.

### Task 2: Wire Validation

**Files:**
- Modify: `app.py`
- Modify: `src/quant_assistant/cli.py`

- [ ] In Streamlit, show validation issues and stop on blocking errors before nested data access.
- [ ] In CLI, print validation errors and return exit code 2 before generating recommendations.

### Task 3: Extract Pure Import Helper

**Files:**
- Modify: `src/quant_assistant/import_review.py`
- Modify: `app.py`
- Modify: `tests/test_import_review.py`

- [ ] Move parsed DataFrame merge logic from `app.py` to `import_review.py`.
- [ ] Add a unit test for duplicate-name merge behavior.

### Task 4: Repo Hygiene Notes

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] Ignore known non-deploy local artifact directories where safe.
- [ ] Document that old projects/videos should stay out of deploy commits.

### Task 5: Verification

**Files:**
- Read only.

- [ ] Run `python -m pytest`.
- [ ] Run CLI snapshot smoke test.
- [ ] Confirm Streamlit responds on localhost.
- [ ] Run `git diff --check`.
