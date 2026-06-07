import json

from quant_assistant.config import load_json, save_json


def test_save_json_creates_parent_directories(tmp_path):
    config_path = tmp_path / "nested" / "config.json"

    save_json(config_path, {"name": "测试", "enabled": True})

    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"name": "测试", "enabled": True}


def test_load_json_uses_quant_assistant_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fallback = tmp_path / "Quant assistant" / "config.json"
    fallback.parent.mkdir()
    fallback.write_text(json.dumps({"source": "fallback"}), encoding="utf-8")

    assert load_json("config.json") == {"source": "fallback"}
