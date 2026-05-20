import importlib
from pathlib import Path

from quant_assistant.llm_advisor import build_llm_prompt, load_deepseek_settings


def test_llm_advisor_module_imports():
    module = importlib.import_module("quant_assistant.llm_advisor")
    assert hasattr(module, "build_llm_context")
    assert hasattr(module, "generate_advice")


def test_load_deepseek_settings_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    env_file = Path(tmp_path) / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=test-key",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                "DEEPSEEK_MODEL=deepseek-v4-flash",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_deepseek_settings(tmp_path)

    assert settings.configured is True
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-flash"


def test_build_llm_prompt_contains_core_sections():
    portfolio = {
        "accounts": {
            "fund": {"total_assets": 10000, "today_pnl": -20},
            "stock": {"total_assets": 5000, "today_pnl": 30, "available_cash": 1200},
        }
    }
    actionable = [
        {"action": "SELL", "instrument": "机器人", "amount": "200 股", "reason": "超过二档止盈线。"},
    ]
    watchlist = [
        {"action": "HOLD", "instrument": "易方达中证500", "amount": "", "reason": "宽基继续观察。"},
    ]
    coverage_issues = [
        {"账户": "股票", "标的": "沃尔核材", "问题": "未知策略标签", "建议": "补充规则。"},
    ]
    quote_freshness = {"status": "可靠", "detail": "行情时间正常"}

    prompt = build_llm_prompt(
        portfolio=portfolio,
        actionable_recommendations=actionable,
        watchlist_recommendations=watchlist,
        coverage_issues=coverage_issues,
        data_source="实时行情",
        quote_freshness=quote_freshness,
    )

    assert "=== 规则引擎动作建议 ===" in prompt
    assert "SELL 机器人 200 股" in prompt
    assert "=== 规则引擎 HOLD 列表 ===" in prompt
    assert "易方达中证500" in prompt
    assert "=== 无策略覆盖/配置提示 ===" in prompt
    assert "沃尔核材" in prompt
