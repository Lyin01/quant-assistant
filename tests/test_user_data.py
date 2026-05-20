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
