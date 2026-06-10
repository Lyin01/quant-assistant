import csv
from pathlib import Path

from quant_assistant.cli import _quote_status_line, _validation_exit_code, main as cli_main


def test_quote_status_line_is_explicit_for_no_live_mode():
    config = {
        "market_provider": {
            "name": "auto",
            "use_live_proxy_for_decisions": True,
        }
    }

    status = _quote_status_line(config, live=False, no_live=True)

    assert "未请求实时行情" in status
    assert "持仓快照" in status


def test_quote_status_line_uses_configured_status_for_live_mode():
    config = {
        "market_provider": {
            "name": "auto",
            "use_live_proxy_for_decisions": True,
        }
    }

    status = _quote_status_line(config, live=True, no_live=False)

    assert "实时行情参与策略判断" in status


def test_quote_status_line_tolerates_bad_market_provider_shape():
    status = _quote_status_line({"market_provider": "bad"}, live=False, no_live=True)

    assert "auto" in status


def test_validation_exit_code_blocks_invalid_input():
    assert _validation_exit_code({}, {"accounts": {}}) == 2


def test_cli_no_live_smoke_does_not_mutate_portfolio_or_write_log(tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "config.json"
    portfolio_path = tmp_path / "portfolio.json"
    config_path.write_bytes((root / "config.json").read_bytes())
    portfolio_path.write_bytes((root / "portfolio.json").read_bytes())
    before_portfolio = portfolio_path.read_bytes()

    monkeypatch.setattr(
        "sys.argv",
        [
            "quant-assistant",
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--no-live",
        ],
    )

    assert cli_main() == 0

    output = capsys.readouterr().out
    assert "行情模式: 本地快照" in output
    assert "未请求实时行情" in output
    assert portfolio_path.read_bytes() == before_portfolio
    assert not (tmp_path / "data" / "journal.csv").exists()


def test_cli_save_log_writes_journal_without_mutating_portfolio(tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "config.json"
    portfolio_path = tmp_path / "portfolio.json"
    config_path.write_bytes((root / "config.json").read_bytes())
    portfolio_path.write_bytes((root / "portfolio.json").read_bytes())
    before_portfolio = portfolio_path.read_bytes()

    monkeypatch.setattr(
        "sys.argv",
        [
            "quant-assistant",
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--no-live",
            "--save-log",
        ],
    )

    assert cli_main() == 0

    output = capsys.readouterr().out
    journal_path = tmp_path / "data" / "journal.csv"
    assert "日志已写入" in output
    assert str(journal_path) in output
    assert portfolio_path.read_bytes() == before_portfolio
    assert journal_path.exists()

    with journal_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert rows
    assert {"time", "action", "instrument", "amount", "reason"} == set(rows[0])
    assert any(row["action"] == "SELL" and row["instrument"] == "机器人" for row in rows)
