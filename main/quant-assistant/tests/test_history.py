import json
from pathlib import Path
from tempfile import TemporaryDirectory

from quant_assistant.history import compute_delta, record_change, read_history, rollback


def test_compute_delta_adds_updates_and_ignores_unchanged():
    existing = [
        {"name": "半导体", "market_value": 200.0, "shares": 100},
        {"name": "机器人", "market_value": 300.0, "shares": 200},
    ]
    imported = [
        {"name": "半导体", "market_value": 250.0, "shares": 100},
        {"name": "沃尔核材", "market_value": 1000.0, "shares": 50},
    ]
    delta = compute_delta(existing, imported)
    assert delta["updated"] == ["半导体"]
    assert delta["added"] == ["沃尔核材"]
    assert delta["removed"] == ["机器人"]


def test_compute_delta_empty_lists_when_no_changes():
    existing = [{"name": "A", "market_value": 100.0}]
    imported = [{"name": "A", "market_value": 100.0}]
    delta = compute_delta(existing, imported)
    assert delta["updated"] == []
    assert delta["added"] == []
    assert delta["removed"] == []


def test_record_and_read_history():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"

        record_change(
            history_file,
            change_type="ocr_import",
            account="stock",
            delta={"added": ["A"], "updated": [], "removed": []},
            summary={"total_assets": 1000.0},
            previous_snapshot={"positions": []},
        )

        history = read_history(history_file)
        assert len(history) == 1
        assert history[0]["type"] == "ocr_import"
        assert history[0]["account"] == "stock"
        assert history[0]["changes"]["added"] == ["A"]


def test_rollback_restores_previous_snapshot():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"
        snapshot = {"positions": [{"name": "半导体", "market_value": 200.0}]}

        record_change(
            history_file,
            change_type="ocr_import",
            account="stock",
            delta={"added": ["A"], "updated": [], "removed": []},
            summary={"total_assets": 1000.0},
            previous_snapshot=snapshot,
        )

        result = rollback(history_file)
        assert result == snapshot
