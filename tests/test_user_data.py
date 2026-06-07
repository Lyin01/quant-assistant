import json

from quant_assistant import user_data


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
