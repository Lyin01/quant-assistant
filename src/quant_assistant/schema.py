from __future__ import annotations

from typing import Any


Issue = dict[str, str]


def validate_app_data(config: dict[str, Any], portfolio: dict[str, Any]) -> list[Issue]:
    return validate_config(config) + validate_portfolio(portfolio)


def validate_config(config: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(config, dict):
        return [_issue("config", "错误", "-", "配置不是 JSON object", "检查 config.json 格式。")]

    cash_plan = config.get("cash_plan")
    if not isinstance(cash_plan, dict):
        issues.append(_issue("config", "错误", "cash_plan", "缺少 cash_plan", "补充 cash_plan 配置。"))
    else:
        for field in ("available_cash_total", "minimum_cash_reserve"):
            if field not in cash_plan or not _is_number(cash_plan.get(field)):
                issues.append(_issue("config", "错误", f"cash_plan.{field}", f"缺少 {field}", "补充数字字段。"))

    if not isinstance(config.get("rules"), dict):
        issues.append(_issue("config", "错误", "rules", "缺少 rules", "补充策略规则配置。"))

    quotes = config.get("quotes")
    if not isinstance(quotes, dict):
        issues.append(_issue("config", "错误", "quotes", "缺少 quotes", "补充行情代理配置。"))
        issues.append(_issue("config", "错误", "quotes.proxies", "缺少 quotes.proxies", "补充标的行情代理映射。"))
    else:
        if not isinstance(quotes.get("proxies"), dict):
            issues.append(_issue("config", "错误", "quotes.proxies", "缺少 quotes.proxies", "补充标的行情代理映射。"))
        if not isinstance(quotes.get("market"), dict):
            issues.append(_issue("config", "提示", "quotes.market", "缺少 quotes.market", "补充市场指数映射可改善总览行情。"))

    if not isinstance(config.get("market_provider", {}), dict):
        issues.append(_issue("config", "错误", "market_provider", "market_provider 格式错误", "保持为 JSON object。"))

    return issues


def validate_portfolio(portfolio: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(portfolio, dict):
        return [_issue("portfolio", "错误", "-", "持仓不是 JSON object", "检查 portfolio.json 格式。")]

    accounts = portfolio.get("accounts")
    if not isinstance(accounts, dict):
        return [_issue("portfolio", "错误", "accounts", "缺少 accounts", "补充 fund 和 stock 账户。")]

    for account_key in ("fund", "stock"):
        account = accounts.get(account_key)
        if not isinstance(account, dict):
            issues.append(_issue("portfolio", "错误", f"accounts.{account_key}", f"缺少 {account_key} 账户", "补充账户对象。"))
            continue

        positions = account.get("positions")
        if not isinstance(positions, list):
            issues.append(_issue("portfolio", "错误", f"accounts.{account_key}.positions", "positions 不是列表", "保持 positions 为数组。"))
            continue

        for index, position in enumerate(positions):
            path = f"accounts.{account_key}.positions[{index}]"
            if not isinstance(position, dict):
                issues.append(_issue("portfolio", "错误", path, "持仓格式错误", "每条持仓应为 JSON object。"))
                continue
            if not str(position.get("name", "")).strip():
                issues.append(_issue("portfolio", "错误", f"{path}.name", "持仓缺少名称", "补充 name 字段。"))
            if not str(position.get("tag", "")).strip():
                issues.append(_issue("portfolio", "提示", f"{path}.tag", "持仓缺少策略标签", "补充 tag 字段。"))

    return issues


def blocking_issue_count(issues: list[Issue]) -> int:
    return sum(1 for issue in issues if issue.get("级别") == "错误")


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _issue(scope: str, level: str, path: str, problem: str, suggestion: str) -> Issue:
    return {
        "范围": scope,
        "级别": level,
        "位置": path,
        "问题": problem,
        "建议": suggestion,
    }
