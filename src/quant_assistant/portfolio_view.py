from __future__ import annotations

import math
from typing import Any


def safe_account(portfolio: Any, account_key: str) -> dict[str, Any]:
    if not isinstance(portfolio, dict):
        return {}
    accounts = portfolio.get("accounts")
    if not isinstance(accounts, dict):
        return {}
    account = accounts.get(account_key)
    return account if isinstance(account, dict) else {}


def safe_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def account_positions(account: Any) -> list[dict[str, Any]]:
    if not isinstance(account, dict):
        return []
    positions = account.get("positions")
    if not isinstance(positions, list):
        return []
    return [position for position in positions if isinstance(position, dict)]
