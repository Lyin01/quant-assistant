# 阶段二：策略扩展 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把硬编码的策略规则从 `strategy.py` 中抽离，变成用户可配置的策略模板。

**架构：** 扩展 `config.json` 增加 `strategy_templates` 和 `strategy_bindings`，重构 `strategy.py` 为模板引擎，保留现有规则作为内置默认模板实现向后兼容。

**技术栈：** Python, pytest

---

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/quant_assistant/strategy_engine.py` | 创建 | 策略模板引擎：条件评估、动作生成 |
| `config.json` | 修改 | 添加 `strategy_templates` 和 `strategy_bindings` |
| `src/quant_assistant/strategy.py` | 修改 | 重构为调用模板引擎，保留内置默认 |
| `tests/test_strategy_engine.py` | 创建 | 模板引擎单元测试 |
| `tests/test_strategy.py` | 修改 | 确保现有测试继续通过（向后兼容） |

---

## 任务 1：创建策略模板引擎

**文件：**
- 创建：`src/quant_assistant/strategy_engine.py`
- 测试：`tests/test_strategy_engine.py`

### Step 1: 编写失败测试

创建 `tests/test_strategy_engine.py`：

```python
import pytest
from quant_assistant.strategy_engine import (
    evaluate_condition,
    evaluate_template,
    build_recommendation,
    resolve_value,
    TemplateContext,
)


def test_evaluate_condition_simple():
    ctx = TemplateContext(daily_pct=2.0, holding_pnl_pct=15.0, price=1.5)
    assert evaluate_condition({"field": "daily_pct", "op": ">=", "value": 1.5}, ctx) is True
    assert evaluate_condition({"field": "daily_pct", "op": ">=", "value": 3.0}, ctx) is False


def test_evaluate_condition_with_value_ref():
    ctx = TemplateContext(daily_pct=2.0, holding_pnl_pct=15.0, price=1.5)
    config_rules = {"sell_profit_pct": 12.0}
    assert evaluate_condition({"field": "holding_pnl_pct", "op": ">=", "value_ref": "sell_profit_pct"}, ctx, config_rules) is True


def test_evaluate_template_all_conditions_met():
    template = {
        "conditions": [
            {"field": "daily_pct", "op": ">=", "value": 1.5},
            {"field": "holding_pnl_pct", "op": ">=", "value": 12.0},
        ],
        "action": {"type": "SELL_MONEY", "amount": 500},
    }
    ctx = TemplateContext(daily_pct=2.0, holding_pnl_pct=15.0)
    result = evaluate_template(template, ctx)
    assert result is not None
    assert result["action_type"] == "SELL_MONEY"
    assert result["amount"] == 500


def test_evaluate_template_not_all_met():
    template = {
        "conditions": [
            {"field": "daily_pct", "op": ">=", "value": 1.5},
        ],
        "action": {"type": "SELL_MONEY", "amount": 500},
    }
    ctx = TemplateContext(daily_pct=1.0)
    result = evaluate_template(template, ctx)
    assert result is None


def test_build_recommendation_sell_money():
    rec = build_recommendation("SELL_MONEY", "测试标的", 500, "止盈")
    assert rec["action"] == "SELL"
    assert rec["amount"] == "500 元"


def test_build_recommendation_buy_shares():
    rec = build_recommendation("BUY_SHARES", "测试标的", 100, "低吸")
    assert rec["action"] == "BUY"
    assert rec["amount"] == "100 股"


def test_resolve_value_hardcoded():
    assert resolve_value({"value": 1.5}, {}) == 1.5


def test_resolve_value_from_ref():
    assert resolve_value({"value_ref": "sell_profit_pct"}, {"sell_profit_pct": 12.0}) == 12.0
```

### Step 2: 运行测试确认失败

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_strategy_engine.py -v
```

### Step 3: 创建 `strategy_engine.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TemplateContext:
    """Context variables available for condition evaluation."""
    daily_pct: float = 0.0
    holding_pnl_pct: float = 0.0
    price: float = 0.0
    deployable_cash: float = 0.0
    shares: int = 0


def evaluate_condition(
    condition: dict[str, Any],
    ctx: TemplateContext,
    config_rules: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a single condition against the context."""
    field = condition.get("field")
    op = condition.get("op")
    raw_value = condition.get("value")
    value_ref = condition.get("value_ref")

    ctx_value = _get_field(ctx, field)
    if ctx_value is None:
        return False

    if value_ref is not None and config_rules is not None:
        compare_value = resolve_value({"value_ref": value_ref}, config_rules)
    else:
        compare_value = raw_value

    if compare_value is None:
        return False

    try:
        ctx_num = float(ctx_value)
        comp_num = float(compare_value)
    except (TypeError, ValueError):
        return False

    operators = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a == b,
    }
    func = operators.get(op)
    if func is None:
        return False
    return func(ctx_num, comp_num)


def evaluate_template(
    template: dict[str, Any],
    ctx: TemplateContext,
    config_rules: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Evaluate all conditions in a template. Returns action dict if all pass, else None."""
    conditions = template.get("conditions", [])
    for condition in conditions:
        if not evaluate_condition(condition, ctx, config_rules):
            return None
    return template.get("action")


def build_recommendation(
    action_type: str,
    instrument: str,
    amount: float | int,
    reason: str,
) -> dict[str, str]:
    """Build a Recommendation dict from action type and parameters."""
    if action_type == "BUY_MONEY":
        return {"action": "BUY", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}
    if action_type == "SELL_MONEY":
        return {"action": "SELL", "instrument": instrument, "amount": f"{amount} 元", "reason": reason}
    if action_type == "BUY_SHARES":
        return {"action": "BUY", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    if action_type == "SELL_SHARES":
        return {"action": "SELL", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    if action_type == "LIMIT_BUY":
        return {"action": "LIMIT_BUY", "instrument": instrument, "amount": f"{amount} 股", "reason": reason}
    return {"action": "HOLD", "instrument": instrument, "amount": "-", "reason": reason}


def resolve_value(spec: dict[str, Any], config_rules: dict[str, Any]) -> Any:
    """Resolve a value specification to an actual value."""
    if "value" in spec:
        return spec["value"]
    ref = spec.get("value_ref")
    if ref and config_rules is not None:
        return config_rules.get(ref)
    return None


def _get_field(ctx: TemplateContext, field: str | None) -> Any:
    if field is None:
        return None
    return getattr(ctx, field, None)
```

### Step 4: 运行测试确认通过

### Step 5: Commit

```bash
git add src/quant_assistant/strategy_engine.py tests/test_strategy_engine.py
git commit -m "feat: add strategy template engine"
```

---

## 任务 2：重构 strategy.py 为模板引擎驱动

**文件：**
- 修改：`src/quant_assistant/strategy.py`
- 修改：`config.json`

### Step 1: 扩展 config.json

在 `config.json` 的 `rules` 同级添加：

```json
  "strategy_templates": {
    "core_dca_hold": {
      "description": "长期定投仓，不按短线波动处理",
      "conditions": [],
      "action": {"type": "HOLD", "reason_template": "{name} 是长期定投仓，不按短线波动处理。"}
    },
    "tactical_sell": {
      "description": "tactical 止盈：涨幅达标+收益达标则卖出",
      "conditions": [
        {"field": "daily_pct", "op": ">=", "value_ref": "sell_daily_pct"},
        {"field": "holding_pnl_pct", "op": ">=", "value_ref": "sell_profit_pct"}
      ],
      "action": {"type": "SELL_MONEY", "amount_ref": "sell_amount", "reason_template": "{name} 涨幅 {daily_pct:.2f}%，持有收益 {holding_pnl_pct:.2f}%，触发止盈。"}
    },
    "tactical_buy": {
      "description": "tactical 低吸：回撤达标则买入",
      "conditions": [
        {"field": "daily_pct", "op": "<=", "value_ref": "buy_pullback_pct"},
        {"field": "deployable_cash", "op": ">=", "value_ref": "buy_amount"}
      ],
      "action": {"type": "BUY_MONEY", "amount_ref": "buy_amount", "reason_template": "{name} 回撤 {daily_pct:.2f}%，触发小额低吸。"}
    },
    "profit_sell": {
      "description": "收益止盈模板",
      "conditions": [
        {"field": "holding_pnl_pct", "op": ">=", "value_ref": "sell_profit_pct"}
      ],
      "action": {"type": "SELL_MONEY" if "amount" else "SELL_SHARES", "amount_ref": "sell_amount", "reason_template": "{name} 收益 {holding_pnl_pct:.2f}%，止盈。"}
    },
    "limit_buy": {
      "description": "限价买入模板",
      "conditions": [
        {"field": "price", "op": "<=", "value_ref": "limit_buy_price"}
      ],
      "action": {"type": "BUY_SHARES", "amount_ref": "limit_buy_shares", "reason_template": "{name} 现价 {price:.3f} 小于等于挂单价 {limit_buy_price:.3f}，允许补一手。"}
    },
    "military_sell": {
      "description": "军工反弹卖出",
      "conditions": [
        {"field": "holding_pnl_pct", "op": ">=", "value": 0},
        {"field": "daily_pct", "op": ">=", "value": 0}
      ],
      "action": {"type": "SELL_MONEY", "amount_ref": "sell_amount", "reason_template": "军工已从亏损修复到 {holding_pnl_pct:.2f}%，按规则反弹后降低暴露。"}
    }
  },
  "strategy_bindings": {
    "core_ai_dca": "core_dca_hold",
    "tactical_ai": "tactical_sell",
    "power_grid": "tactical_sell",
    "military": "military_sell",
    "overseas": "profit_sell",
    "healthcare": "profit_sell",
    "defensive": "profit_sell",
    "semiconductor": "limit_buy",
    "wide_index": "wide_index_buy"
  }
```

注意：这里的设计比较复杂，实际上策略模板需要更仔细地设计。让我简化一下，先做核心的模板引擎集成，保持向后兼容。

实际上，让我重新思考这个实现。阶段二的目标是把硬编码规则变成可配置模板，但这需要非常仔细的设计，因为现有规则有很多特殊逻辑（如半导体有多个条件分支、机器人有区间买入等）。

一个更实际的方案是：
1. 创建模板引擎框架
2. 把简单的规则（tactical_sell, profit_sell）迁移到模板
3. 复杂的规则（semiconductor, robot）保持内置逻辑
4. 允许用户通过 config.json 覆盖或扩展

但为了效率，我可以先实现一个更精简的版本：
- 创建模板引擎
- 重构 strategy.py 中的简单规则（tactical_ai, power_grid, military, overseas, healthcare, defensive）使用模板
- 保留复杂规则（semiconductor, robot, wide_index）的内置逻辑
- 绑定通过 config.json 的 strategy_bindings

让我重新设计任务 2，使其更可行。

实际上，为了效率，让我把整个阶段二的计划简化一些。模板引擎已经在任务 1 中定义了。任务 2 的重点是：
1. 在 config.json 中添加 templates 和 bindings
2. 重构 strategy.py 中的 _fund_recommendations 和 _stock_recommendations，使其优先使用模板
3. 保持向后兼容

让我重写这个计划，使其更具体和可执行。