import csv

from quant_assistant.journal import append_recommendations


def test_append_recommendations_creates_parent_and_csv_rows(tmp_path):
    journal_path = tmp_path / "nested" / "journal.csv"

    append_recommendations(
        journal_path,
        [
            {
                "action": "SELL",
                "instrument": "机器人",
                "amount": "100 股",
                "reason": "触发止盈",
            }
        ],
    )

    assert journal_path.exists()
    with journal_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["action"] == "SELL"
    assert rows[0]["instrument"] == "机器人"
    assert rows[0]["amount"] == "100 股"
    assert rows[0]["reason"] == "触发止盈"
    assert rows[0]["time"]


def test_append_recommendations_appends_without_repeating_header(tmp_path):
    journal_path = tmp_path / "journal.csv"

    append_recommendations(journal_path, [{"action": "HOLD", "instrument": "半导体"}])
    append_recommendations(journal_path, [{"action": "BUY", "instrument": "中证500"}])

    text = journal_path.read_text(encoding="utf-8-sig")
    assert text.count("time,action,instrument,amount,reason") == 1

    with journal_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert [row["action"] for row in rows] == ["HOLD", "BUY"]
    assert [row["instrument"] for row in rows] == ["半导体", "中证500"]


def test_append_recommendations_writes_missing_fields_as_empty_strings(tmp_path):
    journal_path = tmp_path / "journal.csv"

    append_recommendations(journal_path, [{"action": "HOLD"}])

    with journal_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["time"]
    assert rows[0]["action"] == "HOLD"
    assert rows[0]["instrument"] == ""
    assert rows[0]["amount"] == ""
    assert rows[0]["reason"] == ""


def test_append_recommendations_writes_header_when_existing_file_is_empty(tmp_path):
    journal_path = tmp_path / "journal.csv"
    journal_path.write_text("", encoding="utf-8")

    append_recommendations(journal_path, [{"action": "BUY", "instrument": "中证500"}])

    text = journal_path.read_text(encoding="utf-8-sig")
    assert text.startswith("time,action,instrument,amount,reason")

    with journal_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["action"] == "BUY"
    assert rows[0]["instrument"] == "中证500"
