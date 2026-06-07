from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FallbackDeepSeekSettings:
    api_key: str = ""
    base_url: str = ""
    model: str = "unavailable"

    @property
    def configured(self) -> bool:
        return False


@dataclass(frozen=True)
class LLMAdvisorExports:
    build_llm_prompt: Callable[..., str]
    build_local_rule_advice: Callable[..., str]
    diagnose_config: Callable[..., dict[str, Any]]
    load_deepseek_settings: Callable[..., Any]
    request_deepseek_advice: Callable[..., str]
    import_error: str = ""


def load_llm_advisor_exports() -> LLMAdvisorExports:
    try:
        module = importlib.import_module("quant_assistant.llm_advisor")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return LLMAdvisorExports(
            build_llm_prompt=_fallback_build_llm_prompt,
            build_local_rule_advice=_fallback_build_local_rule_advice,
            diagnose_config=_fallback_diagnose_config(error),
            load_deepseek_settings=_fallback_load_deepseek_settings,
            request_deepseek_advice=_fallback_request_deepseek_advice(error),
            import_error=error,
        )

    return LLMAdvisorExports(
        build_llm_prompt=getattr(module, "build_llm_prompt", _fallback_build_llm_prompt),
        build_local_rule_advice=getattr(module, "build_local_rule_advice", _fallback_build_local_rule_advice),
        diagnose_config=getattr(module, "diagnose_config", _fallback_diagnose_config("")),
        load_deepseek_settings=getattr(module, "load_deepseek_settings", _fallback_load_deepseek_settings),
        request_deepseek_advice=getattr(module, "request_deepseek_advice", _fallback_request_deepseek_advice("")),
    )


def _fallback_load_deepseek_settings(project_root: str | Path) -> FallbackDeepSeekSettings:
    return FallbackDeepSeekSettings(api_key=os.getenv("DEEPSEEK_API_KEY", ""))


def _fallback_request_deepseek_advice(import_error: str) -> Callable[..., str]:
    def _request_deepseek_advice(*_: Any, **__: Any) -> str:
        message = "LLM advisor module is unavailable"
        if import_error:
            message = f"{message}: {import_error}"
        raise RuntimeError(message)

    return _request_deepseek_advice


def _fallback_diagnose_config(import_error: str) -> Callable[[str | Path], dict[str, Any]]:
    def _diagnose_config(project_root: str | Path) -> dict[str, Any]:
        root = Path(project_root)
        env_file = root / ".env"
        env_key = os.getenv("DEEPSEEK_API_KEY", "")
        return {
            "project_root": str(root),
            "env_file_exists": env_file.exists(),
            "env_file_path": str(env_file),
            "dotenv_available": False,
            "sources": {
                "env_var": "已配置" if env_key else "未设置",
                "streamlit_secrets": "LLM 模块不可用，未检查",
                "env_file": "已配置" if _env_file_has_key(env_file) else "未配置或不存在",
            },
            "llm_advisor_import_error": import_error or "missing optional llm_advisor export",
        }

    return _diagnose_config


def _fallback_build_llm_prompt(
    portfolio: dict[str, Any],
    actionable_recommendations: list[dict[str, str]],
    watchlist_recommendations: list[dict[str, str]],
    coverage_issues: list[dict[str, str]],
    data_source: str,
    quote_freshness: dict[str, Any],
) -> str:
    return _fallback_build_local_rule_advice(
        portfolio=portfolio,
        actionable_recommendations=actionable_recommendations,
        watchlist_recommendations=watchlist_recommendations,
        coverage_issues=coverage_issues,
        data_source=data_source,
        quote_freshness=quote_freshness,
    )


def _fallback_build_local_rule_advice(
    portfolio: dict[str, Any],
    actionable_recommendations: list[dict[str, str]],
    watchlist_recommendations: list[dict[str, str]],
    coverage_issues: list[dict[str, str]],
    data_source: str,
    quote_freshness: dict[str, Any],
) -> str:
    accounts = portfolio.get("accounts", {})
    fund = accounts.get("fund", {})
    stock = accounts.get("stock", {})
    lines = [
        "### 本地规则摘要（非 LLM）",
        "- LLM 辅助模块加载不完整，当前使用启动兜底，应用其他功能可继续使用。",
        f"- 数据来源：{data_source}；行情状态：{quote_freshness.get('status', '未知')}",
        f"- 基金资产：{_number(fund.get('total_assets')):.2f}；股票资产：{_number(stock.get('total_assets')):.2f}；股票可用现金：{_number(stock.get('available_cash')):.2f}",
        f"- 今日动作 {len(actionable_recommendations)} 条，观察项 {len(watchlist_recommendations)} 条，策略配置提示 {len(coverage_issues)} 条。",
        "",
        "#### 今日动作",
    ]

    lines.extend(_format_recommendations(actionable_recommendations) or ["- 当前没有触发买入、卖出或限价买入动作。"])
    lines.extend(["", "#### 重点观察"])
    lines.extend(_format_recommendations(watchlist_recommendations) or ["- 当前没有 HOLD 观察项。"])
    lines.extend(["", "#### 人工复核"])
    if coverage_issues:
        for issue in coverage_issues[:8]:
            account = issue.get("账户", issue.get("璐︽埛", "未知账户"))
            target = issue.get("标的", issue.get("鏍囩殑", "未知标的"))
            problem = issue.get("问题", issue.get("闂", "待复核"))
            suggestion = issue.get("建议", issue.get("寤鸿", ""))
            lines.append(f"- {account} / {target}: {problem}。{suggestion}")
    else:
        lines.append("- 当前没有明显策略覆盖缺口。")

    lines.append("")
    lines.append("以上为本地兜底摘要，不调用外部模型，不构成收益预测或自动下单。")
    return "\n".join(lines).strip()


def _format_recommendations(recommendations: list[dict[str, str]]) -> list[str]:
    lines = []
    for rec in recommendations[:8]:
        action = rec.get("action", "HOLD")
        instrument = rec.get("instrument", rec.get("name", "未知标的"))
        amount = rec.get("amount", "")
        reason = rec.get("reason", "")
        if amount:
            lines.append(f"- {action} {instrument} {amount}: {reason}")
        else:
            lines.append(f"- {action} {instrument}: {reason}")
    if len(recommendations) > 8:
        lines.append(f"- 其余 {len(recommendations) - 8} 条请查看上方表格。")
    return lines


def _env_file_has_key(env_file: Path) -> bool:
    if not env_file.exists():
        return False
    try:
        return any(line.strip().startswith("DEEPSEEK_API_KEY=") for line in env_file.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if result != result or result in (float("inf"), float("-inf")):
        return 0.0
    return result
