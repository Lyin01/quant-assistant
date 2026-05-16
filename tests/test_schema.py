from quant_assistant.schema import blocking_issue_count, validate_app_data, validate_config, validate_portfolio


def _valid_config():
    return {
        "market_provider": {"name": "auto", "timeout_seconds": 5},
        "cash_plan": {"available_cash_total": 1000, "minimum_cash_reserve": 500},
        "rules": {"wide_index": {}},
        "quotes": {"market": {"上证指数": "1.000001"}, "proxies": {"中证500": "1.000905"}},
    }


def _valid_portfolio():
    return {
        "as_of": "2026-05-15 15:00",
        "accounts": {
            "fund": {
                "total_assets": 1000.0,
                "today_pnl": 10.0,
                "positions": [{"name": "易方达中证500", "tag": "wide_index", "market_value": 1000.0}],
            },
            "stock": {
                "total_assets": 500.0,
                "today_pnl": -1.0,
                "available_cash": 100.0,
                "positions": [{"name": "半导体", "tag": "semiconductor", "market_value": 200.0}],
            },
        },
    }


def test_validate_config_accepts_minimal_valid_config():
    issues = validate_config(_valid_config())

    assert blocking_issue_count(issues) == 0


def test_validate_config_flags_missing_required_sections():
    issues = validate_config({"market_provider": {}})

    problems = {issue["问题"] for issue in issues}
    assert "缺少 cash_plan" in problems
    assert "缺少 rules" in problems
    assert "缺少 quotes.proxies" in problems
    assert blocking_issue_count(issues) >= 3


def test_validate_portfolio_accepts_minimal_valid_portfolio():
    issues = validate_portfolio(_valid_portfolio())

    assert blocking_issue_count(issues) == 0


def test_validate_portfolio_flags_missing_accounts():
    issues = validate_portfolio({"accounts": {"fund": {"positions": []}}})

    problems = {issue["问题"] for issue in issues}
    assert "缺少 stock 账户" in problems
    assert blocking_issue_count(issues) == 1


def test_validate_portfolio_flags_bad_positions():
    portfolio = _valid_portfolio()
    portfolio["accounts"]["fund"]["positions"] = [{"tag": "wide_index"}]

    issues = validate_portfolio(portfolio)

    assert issues[0]["问题"] == "持仓缺少名称"
    assert blocking_issue_count(issues) == 1


def test_validate_app_data_combines_config_and_portfolio_issues():
    issues = validate_app_data({}, {"accounts": {}})

    assert blocking_issue_count(issues) >= 4
    assert any(issue["范围"] == "config" for issue in issues)
    assert any(issue["范围"] == "portfolio" for issue in issues)
