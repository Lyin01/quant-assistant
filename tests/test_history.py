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


def test_compute_delta_ignores_id_and_tiny_numeric_noise():
    existing = [{"id": "old", "name": "A", "market_value": 100.0000001}]
    imported = [{"id": "new", "name": "A", "market_value": 100.0000002}]

    delta = compute_delta(existing, imported)

    assert delta == {"added": [], "updated": [], "removed": []}


def test_compute_delta_skips_malformed_positions():
    existing = [
        "not-a-position",
        {"market_value": 999},
        {"name": "A", "market_value": 100.0},
        {"name": "Removed", "market_value": 50.0},
    ]
    imported = [
        None,
        {"name": "", "market_value": 999},
        {"name": "A", "market_value": 100.0},
        {"name": "New", "market_value": 25.0},
    ]

    delta = compute_delta(existing, imported)

    assert delta == {"added": ["New"], "updated": [], "removed": ["Removed"]}


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


def test_record_change_creates_parent_directory():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "nested" / "history" / "test_history.jsonl"

        record_change(
            history_file,
            change_type="ocr_import",
            account="fund",
            delta={"added": [], "updated": ["A"], "removed": []},
            summary={"total_assets": 1000.0},
        )

        history = read_history(history_file)
        assert history_file.exists()
        assert history[0]["account"] == "fund"
        assert history[0]["changes"]["updated"] == ["A"]


def test_record_change_tolerates_bad_delta_and_summary_shapes():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"

        record_change(
            history_file,
            change_type="ocr_import",
            account="stock",
            delta="bad-delta",
            summary=["bad-summary"],
        )

        history = read_history(history_file)

        assert history[0]["changes"] == {"added": [], "updated": [], "removed": [], "summary": {}}


def test_history_helpers_accept_string_paths():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "history.jsonl"
        snapshot = {"positions": [{"name": "A", "market_value": 100.0}]}

        record_change(
            str(history_file),
            change_type="ocr_import",
            account="stock",
            delta={"added": ["A"], "updated": [], "removed": []},
            summary={"total_assets": 100.0},
            previous_snapshot=snapshot,
        )

        history = read_history(str(history_file))
        assert history[0]["changes"]["added"] == ["A"]
        assert rollback(str(history_file)) == snapshot


def test_read_history_skips_bad_lines_and_returns_newest_first():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"
        history_file.write_text(
            "\n".join(
                [
                    json.dumps({"timestamp": "1", "account": "fund"}, ensure_ascii=False),
                    "{bad json",
                    json.dumps({"timestamp": "2", "account": "stock"}, ensure_ascii=False),
                    "",
                    json.dumps({"timestamp": "3", "account": "fund"}, ensure_ascii=False),
                ]
            ),
            encoding="utf-8",
        )

        history = read_history(history_file, limit=2)

        assert [record["timestamp"] for record in history] == ["3", "2"]


def test_read_history_skips_non_object_json_records():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"
        history_file.write_text(
            "\n".join(
                [
                    json.dumps(["not", "a", "record"], ensure_ascii=False),
                    json.dumps("not a record", ensure_ascii=False),
                    json.dumps({"timestamp": "1", "account": "fund"}, ensure_ascii=False),
                ]
            ),
            encoding="utf-8",
        )

        history = read_history(history_file)

        assert history == [{"timestamp": "1", "account": "fund"}]


def test_read_history_non_positive_limit_returns_empty_list():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"
        history_file.write_text(
            json.dumps({"timestamp": "1", "account": "fund"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        assert read_history(history_file, limit=0) == []
        assert read_history(history_file, limit=-1) == []


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
