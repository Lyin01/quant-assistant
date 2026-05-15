from __future__ import annotations

from typing import Any

import pandas as pd


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if data.empty:
        return data

    data = data.sort_values("date").reset_index(drop=True)
    data["ret"] = data["close"].pct_change()
    for window in [5, 20, 60]:
        data[f"ma{window}"] = data["close"].rolling(window).mean()
    data["high_20"] = data["close"].rolling(20).max()
    data["drawdown_20_pct"] = (data["close"] / data["high_20"] - 1.0) * 100.0
    data["cummax"] = data["close"].cummax()
    data["drawdown_pct"] = (data["close"] / data["cummax"] - 1.0) * 100.0
    return data


def add_advanced_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if data.empty or len(data) < 26:
        return data

    # MACD
    ema12 = data["close"].ewm(span=12, adjust=False).mean()
    ema26 = data["close"].ewm(span=26, adjust=False).mean()
    data["macd"] = ema12 - ema26
    data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()
    data["macd_hist"] = data["macd"] - data["macd_signal"]

    # RSI(14)
    delta = data["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    data["rsi14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands (20, 2)
    data["bb_middle"] = data["close"].rolling(20).mean()
    bb_std = data["close"].rolling(20).std()
    data["bb_upper"] = data["bb_middle"] + 2 * bb_std
    data["bb_lower"] = data["bb_middle"] - 2 * bb_std

    return data


def latest_signal(frame: pd.DataFrame) -> dict[str, Any]:
    data = add_indicators(frame)
    if data.empty:
        return {"signal": "NO_DATA", "reason": "没有历史数据。"}

    latest = data.iloc[-1]
    close = float(latest["close"])
    ma20 = _float_or_none(latest.get("ma20"))
    ma60 = _float_or_none(latest.get("ma60"))
    drawdown = _float_or_none(latest.get("drawdown_20_pct"))

    if ma20 is None or ma60 is None:
        return {
            "signal": "WAIT",
            "reason": "历史数据不足 60 日，暂不生成均线信号。",
            "close": close,
        }

    if close > ma20 > ma60 and drawdown is not None and drawdown > -2:
        signal = "TREND_UP"
        reason = "收盘价在 MA20 / MA60 上方，趋势偏强，不追涨。"
    elif close > ma60 and drawdown is not None and -6 <= drawdown <= -3:
        signal = "PULLBACK_BUY_ZONE"
        reason = "价格仍在 MA60 上方，20 日回撤约 3%-6%，进入低吸观察区。"
    elif close < ma20 and close > ma60:
        signal = "COOLDOWN"
        reason = "跌破 MA20 但仍在 MA60 上方，等待企稳。"
    elif close < ma60:
        signal = "RISK_OFF"
        reason = "跌破 MA60，先防守，不做主动加仓。"
    else:
        signal = "NEUTRAL"
        reason = "信号中性，等待更明确的价格位置。"

    return {
        "signal": signal,
        "reason": reason,
        "close": close,
        "ma20": ma20,
        "ma60": ma60,
        "drawdown_20_pct": drawdown,
    }


def backtest_ma_trend(frame: pd.DataFrame, fast: int = 20, slow: int = 60) -> tuple[pd.DataFrame, dict[str, float]]:
    data = frame.copy().sort_values("date").reset_index(drop=True)
    if len(data) < slow + 5:
        return pd.DataFrame(), {"error": float(len(data))}

    data["ret"] = data["close"].pct_change().fillna(0)
    data["fast_ma"] = data["close"].rolling(fast).mean()
    data["slow_ma"] = data["close"].rolling(slow).mean()
    data["signal"] = ((data["close"] > data["fast_ma"]) & (data["fast_ma"] > data["slow_ma"])).astype(int)
    data["position"] = data["signal"].shift(1).fillna(0)
    data["strategy_ret"] = data["position"] * data["ret"]
    data["equity"] = (1 + data["strategy_ret"]).cumprod()
    data["buy_hold"] = (1 + data["ret"]).cumprod()
    data["trade"] = data["position"].diff().abs().fillna(0)

    metrics = {
        "strategy_return_pct": (float(data["equity"].iloc[-1]) - 1) * 100,
        "buy_hold_return_pct": (float(data["buy_hold"].iloc[-1]) - 1) * 100,
        "max_drawdown_pct": _max_drawdown(data["equity"]) * 100,
        "trades": float(data["trade"].sum()),
        "days": float(len(data)),
    }
    return data, metrics


def action_list(recommendations: list[dict[str, str]]) -> pd.DataFrame:
    rows = [
        {
            "动作": rec["action"],
            "标的": rec["instrument"],
            "数量/金额": rec["amount"],
            "原因": rec["reason"],
        }
        for rec in recommendations
        if rec.get("action") not in {"HOLD"}
    ]
    return pd.DataFrame(rows)


def _max_drawdown(series: pd.Series) -> float:
    running_max = series.cummax()
    drawdown = series / running_max - 1.0
    return float(drawdown.min())


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
