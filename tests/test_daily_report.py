from types import SimpleNamespace

from quant_assistant.daily_report import _tomorrow_plan, generate_daily_report


def _pipe(recommendations=None, risk_findings=None, analysis_findings=None):
    return SimpleNamespace(
        decision_report=SimpleNamespace(data={"recommendations": recommendations or []}),
        risk_report=SimpleNamespace(findings=risk_findings or []),
        analysis_report=SimpleNamespace(findings=analysis_findings or []),
        data_report=SimpleNamespace(findings=[]),
        final_summary="summary",
    )


def test_tomorrow_plan_does_not_add_strategy_task_without_uncovered_risk():
    pipe = _pipe(
        risk_findings=[
            "现金紧张: 股票可用仅 22.23 元",
            "高度集中: 通宇通讯 占股票市值 51.9%",
        ]
    )

    plans = _tomorrow_plan(pipe, cash=22.23)

    assert "现金紧张，明日如有买入计划需先银证转账补充子弹" in plans
    assert "考虑分散持仓，降低单票集中度" in plans
    assert not any("补充策略规则" in plan for plan in plans)


def test_generate_daily_report_tolerates_bad_portfolio_account_shapes(monkeypatch):
    monkeypatch.setattr("quant_assistant.daily_report.run_pipeline", lambda *args, **kwargs: _pipe())

    report = generate_daily_report({}, {"accounts": "bad"}, quotes={})

    assert report["summary"]["total_assets"] == 0
    assert report["summary"]["fund_assets"] == 0
    assert report["summary"]["stock_assets"] == 0


def test_tomorrow_plan_adds_strategy_task_for_uncovered_risk():
    pipe = _pipe(risk_findings=["无策略覆盖: 示例持仓"])

    plans = _tomorrow_plan(pipe, cash=1000)

    assert "补充策略规则: 无策略覆盖: 示例持仓" in plans
