from __future__ import annotations

from typing import Any

import pandas as pd


VALID_ACCOUNTS = {"fund", "stock"}


def detect_target_account(
    preset: str,
    summary: dict[str, Any] | None,
    positions: list[dict[str, Any]],
) -> str:
    summary = summary or {}
    account_type = summary.get("account_type")
    if account_type in VALID_ACCOUNTS:
        return str(account_type)
    if preset == "股票截图":
        return "stock"
    if preset == "基金截图":
        return "fund"
    if any(_has_value(position.get("shares")) for position in positions):
        return "stock"
    return "fund"


def import_review_issues(
    positions: list[dict[str, Any]],
    account: str,
    existing_positions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not positions:
        return [
            _issue(
                "错误",
                "-",
                "未识别到持仓",
                "先补充可解析的持仓行，再确认写入。",
            )
        ]

    existing_names = {str(position.get("name", "")).strip() for position in existing_positions}
    issues: list[dict[str, str]] = []

    for position in positions:
        name = str(position.get("name", "")).strip() or "-"
        tag = str(position.get("tag", "")).strip()

        if not _has_value(position.get("market_value")) or float(position.get("market_value") or 0) <= 0:
            # 降级为提示：截图 OCR 可能漏识别数字，或用户只想更新部分字段（如股数、成本）
            issues.append(_issue("提示", name, "缺少市值", "补充 market_value 后数据更完整；如只更新其他字段可忽略。"))

        if not _has_value(position.get("holding_pnl_pct")):
            issues.append(_issue("提示", name, "缺少持有收益率", "补充 holding_pnl_pct 后建议会更准确。"))

        if account == "stock":
            if not _has_value(position.get("shares")):
                issues.append(_issue("提示", name, "股票持仓缺少股数", "补充 shares，方便生成按股数操作的建议。"))
            if not _has_value(position.get("price")):
                issues.append(_issue("提示", name, "股票持仓缺少现价", "补充 price，或依赖 market_proxy 实时行情。"))
            if not _has_value(position.get("cost")):
                issues.append(_issue("提示", name, "股票持仓缺少成本", "补充 cost，方便计算持仓收益率。"))

        if name not in existing_names and (not tag or tag == "imported"):
            issues.append(
                _issue(
                    "提示",
                    name,
                    "新持仓未选择策略标签",
                    "确认 tag 是否需要从 imported 改成对应策略类型。",
                )
            )

    return issues


def merge_parsed_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty or "name" not in combined.columns:
        return combined
    return combined.drop_duplicates(subset=["name"], keep="last").reset_index(drop=True)


def blocking_issue_count(issues: list[dict[str, str]]) -> int:
    return sum(1 for issue in issues if issue.get("级别") == "错误")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        import pandas as pd

        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _issue(level: str, instrument: str, problem: str, suggestion: str) -> dict[str, str]:
    return {
        "级别": level,
        "标的": instrument,
        "问题": problem,
        "建议": suggestion,
    }
