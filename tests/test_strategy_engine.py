from quant_assistant.strategy_engine import (
    TemplateContext,
    evaluate_condition,
    evaluate_template,
    build_recommendation,
    resolve_value,
)


def test_evaluate_condition_gte():
    ctx = TemplateContext(daily_pct=2.0)
    assert evaluate_condition({"field": "daily_pct", "op": ">=", "value": 1.5}, ctx) is True
    assert evaluate_condition({"field": "daily_pct", "op": ">=", "value": 2.5}, ctx) is False


def test_evaluate_condition_lte():
    ctx = TemplateContext(daily_pct=-2.0)
    assert evaluate_condition({"field": "daily_pct", "op": "<=", "value": -1.5}, ctx) is True
    assert evaluate_condition({"field": "daily_pct", "op": "<=", "value": -2.5}, ctx) is False


def test_evaluate_condition_gt():
    ctx = TemplateContext(holding_pnl_pct=12.0)
    assert evaluate_condition({"field": "holding_pnl_pct", "op": ">", "value": 10.0}, ctx) is True
    assert evaluate_condition({"field": "holding_pnl_pct", "op": ">", "value": 12.0}, ctx) is False


def test_evaluate_condition_lt():
    ctx = TemplateContext(price=1.95)
    assert evaluate_condition({"field": "price", "op": "<", "value": 2.0}, ctx) is True
    assert evaluate_condition({"field": "price", "op": "<", "value": 1.95}, ctx) is False


def test_evaluate_condition_eq():
    ctx = TemplateContext(daily_pct=1.5)
    assert evaluate_condition({"field": "daily_pct", "op": "==", "value": 1.5}, ctx) is True
    assert evaluate_condition({"field": "daily_pct", "op": "==", "value": 1.0}, ctx) is False


def test_evaluate_condition_with_value_ref():
    ctx = TemplateContext(daily_pct=2.0)
    config_rules = {"sell_daily_pct": 1.5}
    condition = {"field": "daily_pct", "op": ">=", "value_ref": "sell_daily_pct"}
    assert evaluate_condition(condition, ctx, config_rules) is True

    config_rules["sell_daily_pct"] = 2.5
    assert evaluate_condition(condition, ctx, config_rules) is False


def test_evaluate_condition_missing_ref_returns_false():
    ctx = TemplateContext(daily_pct=2.0)
    condition = {"field": "daily_pct", "op": ">=", "value_ref": "missing_key"}
    assert evaluate_condition(condition, ctx, {}) is False


def test_evaluate_condition_missing_field_or_op():
    ctx = TemplateContext(daily_pct=2.0)
    assert evaluate_condition({"field": "daily_pct"}, ctx) is False
    assert evaluate_condition({"op": ">="}, ctx) is False


def test_evaluate_condition_invalid_op():
    ctx = TemplateContext(daily_pct=2.0)
    assert evaluate_condition({"field": "daily_pct", "op": "invalid", "value": 1.0}, ctx) is False


def test_evaluate_template_all_conditions_met():
    ctx = TemplateContext(daily_pct=2.0, holding_pnl_pct=15.0)
    template = {
        "conditions": [
            {"field": "daily_pct", "op": ">=", "value": 1.5},
            {"field": "holding_pnl_pct", "op": ">=", "value": 12.0},
        ],
        "action": {"type": "SELL_MONEY", "amount": 500},
    }
    action = evaluate_template(template, ctx)
    assert action == {"type": "SELL_MONEY", "amount": 500}


def test_evaluate_template_condition_not_met():
    ctx = TemplateContext(daily_pct=1.0, holding_pnl_pct=15.0)
    template = {
        "conditions": [
            {"field": "daily_pct", "op": ">=", "value": 1.5},
            {"field": "holding_pnl_pct", "op": ">=", "value": 12.0},
        ],
        "action": {"type": "SELL_MONEY", "amount": 500},
    }
    action = evaluate_template(template, ctx)
    assert action is None


def test_evaluate_template_empty_conditions():
    ctx = TemplateContext()
    template = {
        "conditions": [],
        "action": {"type": "HOLD"},
    }
    action = evaluate_template(template, ctx)
    assert action == {"type": "HOLD"}


def test_evaluate_template_with_value_refs():
    ctx = TemplateContext(daily_pct=2.0, holding_pnl_pct=15.0)
    config_rules = {"sell_daily_pct": 1.5, "sell_profit_pct": 12.0}
    template = {
        "conditions": [
            {"field": "daily_pct", "op": ">=", "value_ref": "sell_daily_pct"},
            {"field": "holding_pnl_pct", "op": ">=", "value_ref": "sell_profit_pct"},
        ],
        "action": {"type": "SELL_MONEY", "amount_ref": "sell_amount"},
    }
    action = evaluate_template(template, ctx, config_rules)
    assert action == {"type": "SELL_MONEY", "amount_ref": "sell_amount"}


def test_build_recommendation_buy_money():
    rec = build_recommendation("BUY_MONEY", "Test Fund", 1000, "Buy reason")
    assert rec["action"] == "BUY"
    assert rec["instrument"] == "Test Fund"
    assert rec["amount"] == "1000 元"
    assert rec["reason"] == "Buy reason"


def test_build_recommendation_sell_money():
    rec = build_recommendation("SELL_MONEY", "Test Fund", 500, "Sell reason")
    assert rec["action"] == "SELL"
    assert rec["amount"] == "500 元"


def test_build_recommendation_buy_shares():
    rec = build_recommendation("BUY_SHARES", "Test Stock", 100, "Buy shares reason")
    assert rec["action"] == "BUY"
    assert rec["amount"] == "100 股"


def test_build_recommendation_sell_shares():
    rec = build_recommendation("SELL_SHARES", "Test Stock", 100, "Sell shares reason")
    assert rec["action"] == "SELL"
    assert rec["amount"] == "100 股"


def test_build_recommendation_limit_buy():
    rec = build_recommendation("LIMIT_BUY", "Test Stock", 100, "Limit buy reason")
    assert rec["action"] == "LIMIT_BUY"
    assert rec["amount"] == "100 股"


def test_build_recommendation_hold():
    rec = build_recommendation("HOLD", "Test Fund", 0, "Hold reason")
    assert rec["action"] == "HOLD"
    assert rec["amount"] == "-"


def test_build_recommendation_unknown_type_defaults_to_hold():
    rec = build_recommendation("UNKNOWN", "Test Fund", 0, "Unknown reason")
    assert rec["action"] == "HOLD"


def test_resolve_value_hardcoded():
    assert resolve_value({"value": 1.5}, None) == 1.5
    assert resolve_value({"value": 100}, {}) == 100


def test_resolve_value_from_ref():
    config_rules = {"sell_profit_pct": 12.0, "sell_amount": 500}
    assert resolve_value({"value_ref": "sell_profit_pct"}, config_rules) == 12.0
    assert resolve_value({"value_ref": "sell_amount"}, config_rules) == 500


def test_resolve_value_missing_ref():
    assert resolve_value({"value_ref": "missing"}, {}) is None
    assert resolve_value({"value_ref": "missing"}, None) is None


def test_resolve_value_no_value_or_ref():
    assert resolve_value({}, {}) is None
    assert resolve_value({"other_key": 1}, {}) is None
