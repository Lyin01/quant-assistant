from quant_assistant.cli import _quote_status_line, _validation_exit_code


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


def test_validation_exit_code_blocks_invalid_input():
    assert _validation_exit_code({}, {"accounts": {}}) == 2
