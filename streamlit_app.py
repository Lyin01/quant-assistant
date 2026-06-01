"""Compatibility entrypoint for Streamlit Community Cloud.

The primary app lives in app.py. Keeping this lightweight wrapper lets
Streamlit Cloud's default entrypoint discovery run the same application.
"""

from app import *  # noqa: F401,F403
