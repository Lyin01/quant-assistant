from quant_assistant.import_review import (
    blocking_issue_count,
    detect_target_account,
    import_review_issues,
    merge_parsed_frames,
)
import pandas as pd


def test_detect_target_account_prefers_summary_account_type():
    result = detect_target_account(
        preset="基金截图",
        summary={"account_type": "stock"},
        positions=[{"name": "半导体"}],
    )

    assert result == "stock"


def test_detect_target_account_uses_preset_when_summary_is_missing():
    assert detect_target_account("股票截图", {}, [{"name": "半导体"}]) == "stock"
    assert detect_target_account("基金截图", {}, [{"name": "易方达中证500"}]) == "fund"


def test_detect_target_account_falls_back_to_shares():
    assert detect_target_account("通用", {}, [{"name": "半导体", "shares": 100}]) == "stock"
    assert detect_target_account("通用", {}, [{"name": "易方达中证500"}]) == "fund"


def test_import_review_blocks_empty_import():
    issues = import_review_issues([], account="stock", existing_positions=[])

    assert blocking_issue_count(issues) == 1
    assert issues[0]["级别"] == "错误"
    assert issues[0]["问题"] == "未识别到持仓"


def test_import_review_flags_missing_market_value_and_profit_rate():
    issues = import_review_issues(
        [{"name": "创新药", "tag": "healthcare"}],
        account="fund",
        existing_positions=[],
    )

    problems = {issue["问题"] for issue in issues}
    assert "缺少市值" in problems
    assert "缺少持有收益率" in problems


def test_import_review_flags_stock_specific_missing_fields():
    issues = import_review_issues(
        [{"name": "半导体", "tag": "semiconductor", "market_value": 203.5}],
        account="stock",
        existing_positions=[],
    )

    problems = {issue["问题"] for issue in issues}
    assert "股票持仓缺少股数" in problems
    assert "股票持仓缺少现价" in problems
    assert "股票持仓缺少成本" in problems


def test_import_review_warns_new_imported_tag():
    issues = import_review_issues(
        [{"name": "沃尔核材", "tag": "imported", "market_value": 2249.0}],
        account="stock",
        existing_positions=[{"name": "半导体", "tag": "semiconductor"}],
    )

    assert blocking_issue_count(issues) == 0
    matching = [issue for issue in issues if issue["问题"] == "新持仓未选择策略标签"]
    assert matching
    assert matching[0]["级别"] == "提示"


def test_import_review_does_not_warn_existing_imported_tag():
    issues = import_review_issues(
        [{"name": "沃尔核材", "tag": "imported", "market_value": 2249.0}],
        account="stock",
        existing_positions=[{"name": "沃尔核材", "tag": "imported"}],
    )

    problems = {issue["问题"] for issue in issues}
    assert "新持仓未选择策略标签" not in problems


def test_merge_parsed_frames_keeps_latest_duplicate_name():
    first = pd.DataFrame([{"name": "半导体", "market_value": 100.0}])
    second = pd.DataFrame([{"name": "半导体", "market_value": 200.0}, {"name": "创新药", "market_value": 50.0}])

    merged = merge_parsed_frames([first, second])

    assert list(merged["name"]) == ["半导体", "创新药"]
    assert merged.loc[0, "market_value"] == 200.0
