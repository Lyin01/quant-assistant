from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TemplateContext:
    daily_pct: float = 0.0
    holding_pnl_pct: float = 0.0
    price: float = 0.0
    deployable_cash: float = 0.0


def evaluate_condition(condition: dict[str, Any], ctx: TemplateContext, config_rules: dict[str, Any] | None = None) -> bool:
    """Evaluate a single condition against the template context.

    Condition format: {"field": "daily_pct", "op": ">=", "value": 1.5}
    Or with value_ref: {"field": "daily_pct", "op": ">=", "value_ref": "sell_daily_pct"}
    """
    if not isinstance(condition, dict):
        return False

    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")
    value_ref = condition.get("value_ref")

    if field is None or op is None:
        return False

    if value_ref is not None:
        value = resolve_value({"value_ref": value_ref}, config_rules)
        if value is None:
            return False

    if value is None:
        return False

    try:
        field_value = float(getattr(ctx, field, 0))
        compare_value = float(value)
    except (TypeError, ValueError):
        return False

    ops = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }

    if op not in ops:
        return False

    return ops[op](field_value, compare_value)


def evaluate_template(template: dict[str, Any], ctx: TemplateContext, config_rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Evaluate all conditions in a template. Returns action dict if all pass, else None."""
    if not isinstance(template, dict):
        return None

    conditions = template.get("conditions", [])
    if not isinstance(conditions, list):
        return None

    for condition in conditions:
        if not evaluate_condition(condition, ctx, config_rules):
            return None

    return template.get("action")


def build_recommendation(action_type: str, instrument: str, amount: float | int, reason: str) -> dict[str, str]:
    """Build recommendation dict.

    Supports: BUY_MONEY, SELL_MONEY, BUY_SHARES, SELL_SHARES, LIMIT_BUY, HOLD
    """
    if action_type == "BUY_MONEY":
        return {"action": "BUY", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}
    elif action_type == "SELL_MONEY":
        return {"action": "SELL", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}
    elif action_type == "BUY_SHARES":
        return {"action": "BUY", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    elif action_type == "SELL_SHARES":
        return {"action": "SELL", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    elif action_type == "LIMIT_BUY":
        return {"action": "LIMIT_BUY", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    elif action_type == "HOLD":
        return {"action": "HOLD", "instrument": instrument, "amount": "—", "reason": reason}
    else:
        return {"action": "HOLD", "instrument": instrument, "amount": "—", "reason": reason}


def resolve_value(spec: dict[str, Any], config_rules: dict[str, Any] | None) -> Any:
    """Resolve a value specification.

    {"value": 1.5} -> 1.5
    {"value_ref": "sell_profit_pct"} -> looks up in config_rules
    """
    if not isinstance(spec, dict):
        return None

    if "value" in spec:
        return spec["value"]

    if "value_ref" in spec and config_rules is not None:
        ref_key = spec["value_ref"]
        return config_rules.get(ref_key)

    return None
