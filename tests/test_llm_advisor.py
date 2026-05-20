import importlib


def test_llm_advisor_module_imports():
    module = importlib.import_module("quant_assistant.llm_advisor")

    assert hasattr(module, "build_llm_context")
    assert hasattr(module, "generate_advice")
