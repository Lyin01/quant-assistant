import importlib
import sys
import types
from pathlib import Path

from quant_assistant.llm_advisor import (
    build_deepseek_secrets_toml,
    build_llm_context,
    build_llm_prompt,
    build_local_rule_advice,
    diagnose_config,
    load_deepseek_settings,
)


def test_llm_advisor_module_imports():
    module = importlib.import_module("quant_assistant.llm_advisor")
    assert hasattr(module, "build_llm_context")
    assert hasattr(module, "generate_advice")
    assert hasattr(module, "diagnose_config")


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
                "DEEPSEEK_MODEL=deepseek-v4-pro",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_deepseek_settings(tmp_path)

    assert settings.configured is True
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-pro"


def test_load_deepseek_settings_prefers_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")

    settings = load_deepseek_settings(tmp_path)

    assert settings.api_key == "env-key"
    assert settings.base_url == "https://env.example.com"
    assert settings.model == "env-model"


def test_build_deepseek_secrets_toml_quotes_string_values():
    snippet = build_deepseek_secrets_toml("sk-test", model="deepseek-chat")

    assert 'DEEPSEEK_API_KEY = "sk-test"' in snippet
    assert 'DEEPSEEK_BASE_URL = "https://api.deepseek.com"' in snippet
    assert 'DEEPSEEK_MODEL = "deepseek-chat"' in snippet
    assert "DEEPSEEK_API_KEY=sk-test" not in snippet


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


def test_build_llm_context_handles_bad_numeric_values():
    config = {"rules": {"short_term": {}}, "quotes": {"proxies": {}}}
    portfolio = {
        "accounts": {
            "fund": {
                "total_assets": "nan",
                "today_pnl": "bad",
                "positions": ["not-a-position"],
            },
            "stock": {
                "total_assets": "inf",
                "market_value": "100",
                "available_cash": "bad",
                "holding_pnl": float("nan"),
                "positions": [
                    {
                        "name": "Bad OCR",
                        "tag": "imported",
                        "market_value": "bad",
                        "holding_pnl_pct": "nan",
                        "shares": "bad",
                        "price": "inf",
                        "cost": True,
                    },
                    {"name": "Top", "tag": "short_term", "market_value": "80"},
                ],
            },
        }
    }

    ctx = build_llm_context(config, portfolio, recommendations=[])

    assert ctx["total_assets"] == 0.0
    assert ctx["fund"]["position_count"] == 0
    assert ctx["stock"]["available_cash"] == 0.0
    assert ctx["stock"]["holding_pnl"] == 0.0
    assert ctx["concentration"]["top_name"] == "Top"
    assert ctx["concentration"]["top_market_value"] == 80.0
    assert ctx["concentration"]["concentration_pct"] == 80.0
    assert ctx["uncovered_positions"] == [
        {
            "account": "stock",
            "name": "Bad OCR",
            "tag": "imported",
            "market_value": 0.0,
            "holding_pnl_pct": 0.0,
            "shares": 0,
            "price": 0.0,
            "cost": 0.0,
        }
    ]


def test_build_llm_prompt_handles_bad_account_numbers():
    portfolio = {
        "accounts": {
            "fund": {"total_assets": "bad", "today_pnl": "nan"},
            "stock": {"total_assets": "inf", "today_pnl": True, "available_cash": "bad"},
        }
    }

    prompt = build_llm_prompt(
        portfolio=portfolio,
        actionable_recommendations=[],
        watchlist_recommendations=[],
        coverage_issues=[],
        data_source="snapshot",
        quote_freshness={},
    )

    assert "0.00" in prompt


def test_build_local_rule_advice_summarizes_without_api_key():
    portfolio = {
        "accounts": {
            "fund": {"total_assets": 10000},
            "stock": {"total_assets": 5000, "available_cash": 1200},
        }
    }

    advice = build_local_rule_advice(
        portfolio=portfolio,
        actionable_recommendations=[
            {"action": "SELL", "instrument": "机器人", "amount": "100 股", "reason": "触发止盈。"},
        ],
        watchlist_recommendations=[
            {"action": "HOLD", "instrument": "半导体", "amount": "", "reason": "等待价格回落。"},
        ],
        coverage_issues=[
            {"账户": "股票", "标的": "Alpha", "问题": "缺少行情代理", "建议": "补充 market_proxy。"},
        ],
        data_source="持仓快照",
        quote_freshness={"reliable": False, "status": "过期", "detail": "未获取到实时行情。"},
    )

    assert "本地规则摘要（非 LLM）" in advice
    assert "SELL 机器人 100 股" in advice
    assert "HOLD 半导体" in advice
    assert "Alpha" in advice
    assert "不调用外部模型" in advice


def test_diagnose_config_returns_expected_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    env_file = Path(tmp_path) / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key-12345678\n", encoding="utf-8")

    diag = diagnose_config(tmp_path)

    assert diag["env_file_exists"] is True
    assert "project_root" in diag
    assert "sources" in diag
    assert "env_var" in diag["sources"]
    assert "streamlit_secrets" in diag["sources"]
    assert "env_file" in diag["sources"]
    # .env file should be detected as configured
    assert "已配置" in diag["sources"]["env_file"]
    # env var should not be set
    assert diag["sources"]["env_var"] == "未设置"


def test_diagnose_config_no_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    diag = diagnose_config(tmp_path)

    assert diag["env_file_exists"] is False
    assert diag["sources"]["env_file"] == "未配置或不存在"


def test_load_deepseek_settings_from_nested_streamlit_secrets(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.secrets = {
        "oauth": {
            "github": {
                "client_id": "abc",
                "DEEPSEEK_API_KEY": "nested-key",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                "DEEPSEEK_MODEL": "deepseek-v4-pro",
            }
        }
    }
    fake_errors = types.ModuleType("streamlit.errors")
    fake_errors.StreamlitSecretNotFoundError = RuntimeError

    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setitem(sys.modules, "streamlit.errors", fake_errors)

    settings = load_deepseek_settings(tmp_path)

    assert settings.configured is True
    assert settings.api_key == "nested-key"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-pro"
