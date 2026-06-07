import importlib
import sys
import types
from pathlib import Path


def test_app_uses_llm_advisor_compat_layer():
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "from quant_assistant.llm_advisor import" not in app_source
    assert "from quant_assistant.llm_advisor_compat import load_llm_advisor_exports" in app_source


def test_llm_advisor_exports_falls_back_when_local_advice_symbol_missing(monkeypatch):
    fake_module = types.ModuleType("quant_assistant.llm_advisor")
    fake_module.build_llm_prompt = lambda **_: "real prompt"
    fake_module.diagnose_config = lambda project_root: {"project_root": str(project_root)}

    class Settings:
        configured = False

    fake_module.load_deepseek_settings = lambda project_root: Settings()
    fake_module.request_deepseek_advice = lambda *_, **__: "real advice"

    monkeypatch.setitem(sys.modules, "quant_assistant.llm_advisor", fake_module)
    sys.modules.pop("quant_assistant.llm_advisor_compat", None)

    compat = importlib.import_module("quant_assistant.llm_advisor_compat")
    exports = compat.load_llm_advisor_exports()

    assert exports.import_error == ""
    assert exports.build_llm_prompt(
        portfolio={},
        actionable_recommendations=[],
        watchlist_recommendations=[],
        coverage_issues=[],
        data_source="snapshot",
        quote_freshness={},
    ) == "real prompt"

    advice = exports.build_local_rule_advice(
        portfolio={"accounts": {"fund": {}, "stock": {}}},
        actionable_recommendations=[],
        watchlist_recommendations=[],
        coverage_issues=[],
        data_source="snapshot",
        quote_freshness={"status": "stale"},
    )
    assert "LLM" in advice
    assert "snapshot" in advice


def test_llm_advisor_exports_keep_booting_when_module_import_fails(monkeypatch):
    sys.modules.pop("quant_assistant.llm_advisor", None)
    sys.modules.pop("quant_assistant.llm_advisor_compat", None)
    real_import_module = importlib.import_module

    def import_with_llm_failure(name, *args, **kwargs):
        if name == "quant_assistant.llm_advisor":
            raise ImportError("simulated stale cloud module")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", import_with_llm_failure)
    compat = real_import_module("quant_assistant.llm_advisor_compat")
    exports = compat.load_llm_advisor_exports()

    assert "simulated stale cloud module" in exports.import_error
    settings = exports.load_deepseek_settings(".")
    assert settings.configured is False
    diag = exports.diagnose_config(".")
    assert "llm_advisor_import_error" in diag
