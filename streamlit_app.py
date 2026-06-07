"""Compatibility entrypoint for Streamlit Community Cloud."""

from pathlib import Path
import runpy
import traceback

import streamlit as st


DEPLOYMENT_STAMP = "2026-06-08-llm-import-guard"


try:
    runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
except ImportError as exc:
    st.error(f"Streamlit Cloud import failed during bootstrap ({DEPLOYMENT_STAMP}): {exc}")
    st.code(traceback.format_exc())
    st.stop()
