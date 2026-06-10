import json

from quant_assistant import user_data


def test_load_config_backs_up_bad_user_json_and_falls_back(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    user = {"provider": "github", "id": "tester"}
    user_dir = tmp_path / "data" / "users" / "github_tester"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "config.json").write_text("{bad json", encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps({"source": "global"}), encoding="utf-8")

    config = user_data.load_config(user)

    assert config == {"source": "global"}
    assert not (user_dir / "config.json").exists()
    assert (user_dir / "config.json.invalid-1").exists()


def test_get_or_create_portfolio_backs_up_bad_json_and_keeps_app_bootable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    user = {"provider": "github", "id": "tester"}
    user_dir = tmp_path / "data" / "users" / "github_tester"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "portfolio.json").write_text("{bad json", encoding="utf-8")

    portfolio = user_data.get_or_create_portfolio(user)

    assert portfolio["accounts"]["stock"]["positions"] == []
    assert portfolio["accounts"]["fund"]["positions"] == []
    assert not (user_dir / "portfolio.json").exists()
    assert (user_dir / "portfolio.json.invalid-1").exists()


def test_user_id_preserves_email_safe_characters():
    user = {"provider": "github", "email": "a.b+c-d@example.com"}

    assert user_data._user_id(user) == "github_a.b+c-d@example.com"


def test_user_dir_sanitizes_path_fragments(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    user = {"provider": "../github", "id": r"..\evil/user..name"}

    directory = user_data._user_dir(user)

    users_root = (tmp_path / "data" / "users").resolve()
    assert directory.resolve().is_relative_to(users_root)
    assert directory.name == "github_evil_user_name"


def test_get_or_create_portfolio_reconciles_inconsistent_stock_profit_pct(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    user = {"provider": "github", "id": "tester"}
    user_dir = tmp_path / "data" / "users" / "github_tester"
    user_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "as_of": "2026-05-20 15:00",
        "accounts": {
            "fund": {
                "total_assets": 0.0,
                "today_pnl": 0.0,
                "positions": [],
            },
            "stock": {
                "total_assets": 4967.0,
                "today_pnl": 0.0,
                "available_cash": 0.0,
                "positions": [
                    {
                        "name": "通宇通讯",
                        "tag": "imported",
                        "shares": 100,
                        "price": 49.67,
                        "cost": 52.223,
                        "market_value": 4967.0,
                        "holding_pnl": -255.05,
                        "holding_pnl_pct": 88.0,
                    }
                ],
            },
        },
    }
    (user_dir / "portfolio.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    portfolio = user_data.get_or_create_portfolio(user)
    position = portfolio["accounts"]["stock"]["positions"][0]

    assert round(position["holding_pnl_pct"], 2) == -4.88


def test_get_or_create_portfolio_keeps_index_like_stock_lots(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    user = {"provider": "github", "id": "tester"}
    user_dir = tmp_path / "data" / "users" / "github_tester"
    user_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "as_of": "2026-06-01 16:00",
        "accounts": {
            "fund": {
                "total_assets": 0.0,
                "today_pnl": 0.0,
                "positions": [],
            },
            "stock": {
                "total_assets": 9260.74,
                "today_pnl": 88.30,
                "market_value": 4404.70,
                "available_cash": 4856.04,
                "positions": [
                    {
                        "name": "纳指大成",
                        "tag": "overseas",
                        "market_proxy": "纳指",
                        "shares": 900,
                        "price": 1.93,
                        "cost": 1.725,
                        "market_value": 1737.0,
                    },
                    {
                        "name": "易方达中证500",
                        "tag": "wide_index",
                        "market_value": 5703.33,
                    },
                ],
            },
        },
    }
    (user_dir / "portfolio.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    portfolio = user_data.get_or_create_portfolio(user)
    names = [position["name"] for position in portfolio["accounts"]["stock"]["positions"]]

    assert "纳指大成" in names
    assert "易方达中证500" not in names


def test_get_or_create_portfolio_drops_stale_stock_position_matching_summary(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    user = {"provider": "github", "id": "tester"}
    user_dir = tmp_path / "data" / "users" / "github_tester"
    user_dir.mkdir(parents=True, exist_ok=True)

    current_positions = [
        {"name": "沃尔核材", "tag": "imported", "market_value": 2236.0, "shares": 100},
        {"name": "纳指大成", "tag": "overseas", "market_value": 1737.0, "shares": 900},
        {"name": "创新药", "tag": "healthcare", "market_value": 227.1, "shares": 300},
        {"name": "半导体", "tag": "semiconductor", "market_value": 204.6, "shares": 100},
    ]
    payload = {
        "as_of": "2026-06-01 16:00",
        "accounts": {
            "fund": {
                "total_assets": 0.0,
                "today_pnl": 0.0,
                "positions": [],
            },
            "stock": {
                "total_assets": 9260.74,
                "today_pnl": 88.30,
                "market_value": 4404.70,
                "available_cash": 4856.04,
                "positions": current_positions
                + [{"name": "机器人", "tag": "robot", "market_value": 357.6, "shares": 300}],
            },
        },
    }
    (user_dir / "portfolio.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    portfolio = user_data.get_or_create_portfolio(user)
    names = [position["name"] for position in portfolio["accounts"]["stock"]["positions"]]

    assert names == ["沃尔核材", "纳指大成", "创新药", "半导体"]
