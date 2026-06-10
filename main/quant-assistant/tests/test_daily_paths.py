from pathlib import Path

from quant_assistant.config import load_json
from quant_assistant.user_data import find_default_file


def test_load_json_falls_back_to_quant_assistant_directory():
    config = load_json("config.json")

    assert "cash_plan" in config


def test_find_default_file_prefers_repository_root():
    path = find_default_file("portfolio.json")

    assert path == Path("portfolio.json")
