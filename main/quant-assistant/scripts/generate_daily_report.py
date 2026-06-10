#!/usr/bin/env python3
"""CLI script to generate daily report.

Usage:
    cd E:\PROJECT FROM CODEX
    unset PYTHONHOME && /e/python/python.exe scripts/generate_daily_report.py

Outputs:
    reports/report_YYYY-MM-DD.md
    reports/report_YYYY-MM-DD.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.daily_report import generate_daily_report, save_daily_report
from quant_assistant.data_provider import AutoProvider, collect_secids
from quant_assistant.user_data import load_config, get_or_create_portfolio


def main() -> None:
    # Load global config/portfolio (non-authenticated mode for cron)
    config_path = ROOT / "config.json"
    portfolio_path = ROOT / "portfolio.json"

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    with portfolio_path.open("r", encoding="utf-8") as f:
        portfolio = json.load(f)

    provider = AutoProvider()
    secids = collect_secids(config, portfolio)
    quotes = provider.get_quotes(secids) if secids else {}

    report = generate_daily_report(config, portfolio, quotes=quotes, scan_top_n=10)
    md_path = save_daily_report(report, directory=ROOT / "reports")

    print(f"Daily report generated: {md_path}")
    print(f"  Total assets: {report['summary']['total_assets']:.2f}")
    print(f"  Today PnL: {report['summary']['today_pnl']:.2f}")
    print(f"  Actionable: {report['summary']['actionable_count']} items")


if __name__ == "__main__":
    main()
