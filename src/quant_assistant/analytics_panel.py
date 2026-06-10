from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def load_portfolio_history(history_file: str | Path) -> pd.DataFrame:
    """Load portfolio history into a DataFrame for analysis."""
    target = Path(history_file)
    if not target.exists():
        return pd.DataFrame()

    records = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if not isinstance(rec, dict):
                        continue
                    ts = rec.get("timestamp", "")
                    timestamp = pd.to_datetime(ts, errors="coerce")
                    if pd.isna(timestamp):
                        continue
                    changes = rec.get("changes", {})
                    if not isinstance(changes, dict):
                        continue
                    summary = changes.get("summary", {})
                    if not isinstance(summary, dict):
                        continue
                    total_assets = summary.get("total_assets")
                    if total_assets is not None:
                        total_assets_value = float(total_assets)
                        if not pd.notna(total_assets_value) or total_assets_value in (float("inf"), float("-inf")):
                            continue
                        records.append({
                            "timestamp": timestamp,
                            "total_assets": total_assets_value,
                            "account": rec.get("account", "unknown"),
                        })
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    except OSError:
        return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    return df


def compute_return_curve(history_df: pd.DataFrame) -> pd.DataFrame:
    """Compute cumulative return curve from portfolio history."""
    if history_df.empty or len(history_df) < 2:
        return pd.DataFrame()

    df = _clean_history_metrics_frame(history_df)
    if len(df) < 2:
        return pd.DataFrame()
    initial = df["total_assets"].iloc[0]
    if initial <= 0:
        return pd.DataFrame()

    df["cumulative_return_pct"] = (df["total_assets"] / initial - 1) * 100
    return df


def compute_monthly_returns(history_df: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly returns from portfolio history."""
    if history_df.empty or len(history_df) < 2:
        return pd.DataFrame()

    df = _clean_history_metrics_frame(history_df)
    if len(df) < 2:
        return pd.DataFrame()
    df["year_month"] = df["timestamp"].dt.to_period("M")
    monthly = df.groupby("year_month")["total_assets"].agg(["first", "last"]).reset_index()
    monthly = monthly[monthly["first"] > 0].copy()
    if monthly.empty:
        return pd.DataFrame()
    monthly["return_pct"] = (monthly["last"] / monthly["first"] - 1) * 100
    monthly["year"] = monthly["year_month"].dt.year
    monthly["month"] = monthly["year_month"].dt.month
    return monthly


def compute_risk_metrics(history_df: pd.DataFrame) -> dict[str, float]:
    """Compute risk metrics from portfolio history."""
    if history_df.empty or len(history_df) < 2:
        return {}

    df = _clean_history_metrics_frame(history_df)
    df = df[df["total_assets"] > 0].reset_index(drop=True)
    if len(df) < 2:
        return {}
    values = df["total_assets"].values

    # Max drawdown
    cummax = pd.Series(values).cummax()
    drawdowns = (values / cummax - 1) * 100
    max_drawdown = drawdowns.min()

    # Volatility (daily, annualized)
    returns = pd.Series(values).pct_change().dropna()
    if len(returns) > 1:
        daily_vol = returns.std()
        annual_vol = daily_vol * (252 ** 0.5) * 100
    else:
        annual_vol = 0.0

    # Sharpe ratio (assume 2% risk-free rate)
    if len(returns) > 1 and annual_vol > 0:
        total_return = (values[-1] / values[0] - 1)
        years = max((df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days / 365, 0.01)
        annual_return = (1 + total_return) ** (1 / years) - 1
        sharpe = ((annual_return - 0.02) / (annual_vol / 100)) if annual_vol > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "max_drawdown_pct": max_drawdown,
        "annual_volatility_pct": annual_vol,
        "sharpe_ratio": sharpe,
    }


def _clean_history_metrics_frame(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty or not {"timestamp", "total_assets"} <= set(history_df.columns):
        return pd.DataFrame()

    df = history_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df["total_assets"] = pd.to_numeric(df["total_assets"], errors="coerce")
    df = df.dropna(subset=["timestamp", "total_assets"])
    return df.sort_values("timestamp").reset_index(drop=True)


def _float_or_zero(value: Any) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if pd.isna(parsed) else parsed


def build_asset_distribution(portfolio: dict[str, Any]) -> pd.DataFrame:
    """Build asset distribution DataFrame from portfolio."""
    rows = []
    accounts = portfolio.get("accounts", {})
    if not isinstance(accounts, dict):
        return pd.DataFrame()

    for account_key, account in accounts.items():
        if not isinstance(account, dict):
            continue
        account_name = account.get("name", account_key)
        positions = account.get("positions", [])
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            tag = pos.get("tag", "unknown")
            tag_display = {
                "wide_index": "宽基",
                "tactical_ai": "AI战术",
                "power_grid": "电网",
                "military": "军工",
                "semiconductor": "半导体",
                "robot": "机器人",
                "overseas": "海外",
                "healthcare": "医药",
                "defensive": "防御",
                "core_ai_dca": "AI定投",
                "imported": "未分类",
            }.get(tag, tag)
            rows.append({
                "account": account_name,
                "tag": tag_display,
                "name": pos.get("name", ""),
                "market_value": _float_or_zero(pos.get("market_value")),
            })

    return pd.DataFrame(rows)
