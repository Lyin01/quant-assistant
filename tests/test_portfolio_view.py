from quant_assistant.portfolio_view import account_positions, safe_account, safe_number


def test_safe_account_returns_empty_dict_for_bad_account_shapes():
    assert safe_account({"accounts": "bad"}, "stock") == {}
    assert safe_account({"accounts": {"stock": "bad"}}, "stock") == {}
    assert safe_account("bad", "stock") == {}


def test_safe_number_rejects_non_finite_and_boolean_values():
    assert safe_number("12.5") == 12.5
    assert safe_number("nan") == 0.0
    assert safe_number("inf") == 0.0
    assert safe_number(True) == 0.0
    assert safe_number("bad", default=-1.0) == -1.0


def test_account_positions_returns_only_mapping_positions():
    account = {"positions": [{"name": "A"}, "bad", {"name": "B"}]}

    assert account_positions(account) == [{"name": "A"}, {"name": "B"}]
    assert account_positions({"positions": "bad"}) == []
