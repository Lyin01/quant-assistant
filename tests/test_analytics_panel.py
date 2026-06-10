import json
from pathlib import Path

import pandas as pd
import pytest

from quant_assistant.analytics_panel import (
    build_asset_distribution,
    compute_monthly_returns,
    compute_return_curve,
    compute_risk_metrics,
    load_portfolio_history,
)


def test_load_portfolio_history_empty_file(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    history_file.write_text("", encoding="utf-8")
    df = load_portfolio_history(history_file)
    assert df.empty


def test_load_portfolio_history_missing_file(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    df = load_portfolio_history(history_file)
    assert df.empty


def test_load_portfolio_history_directory_path_returns_empty(tmp_path: Path):
    df = load_portfolio_history(tmp_path)

    assert df.empty


def test_load_portfolio_history_valid_records(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    records = [
        {"timestamp": "2024-01-01T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10000}}},
        {"timestamp": "2024-01-02T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10500}}},
        {"timestamp": "2024-01-03T10:00:00", "account": "stock", "changes": {"summary": {"total_assets": 5000}}},
    ]
    history_file.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    df = load_portfolio_history(history_file)
    assert len(df) == 3
    assert list(df.columns) == ["timestamp", "total_assets", "account"]
    assert df["total_assets"].tolist() == [10000.0, 10500.0, 5000.0]
    assert df["account"].tolist() == ["fund", "fund", "stock"]


def test_load_portfolio_history_accepts_string_path(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    history_file.write_text(
        json.dumps(
            {
                "timestamp": "2024-01-01T10:00:00",
                "account": "fund",
                "changes": {"summary": {"total_assets": 10000}},
            }
        ),
        encoding="utf-8",
    )

    df = load_portfolio_history(str(history_file))

    assert len(df) == 1
    assert df["total_assets"].iloc[0] == 10000.0


def test_load_portfolio_history_skips_bad_lines(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    history_file.write_text(
        '{"timestamp": "2024-01-01T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10000}}}\n'
        "not valid json\n"
        '{"timestamp": "2024-01-02T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10500}}}',
        encoding="utf-8",
    )
    df = load_portfolio_history(history_file)
    assert len(df) == 2
    assert df["total_assets"].tolist() == [10000.0, 10500.0]


def test_load_portfolio_history_skips_bad_json_shapes(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    records = [
        ["not", "a", "record"],
        {"timestamp": "bad timestamp", "account": "fund", "changes": {"summary": {"total_assets": 10000}}},
        {"timestamp": "2024-01-01T10:00:00", "account": "fund", "changes": []},
        {"timestamp": "2024-01-02T10:00:00", "account": "fund", "changes": {"summary": []}},
        {"timestamp": "2024-01-03T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": "bad"}}},
        {"timestamp": "2024-01-04T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 11000}}},
    ]
    history_file.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    df = load_portfolio_history(history_file)

    assert len(df) == 1
    assert df["timestamp"].iloc[0] == pd.Timestamp("2024-01-04T10:00:00")
    assert df["total_assets"].iloc[0] == 11000.0


def test_load_portfolio_history_skips_records_without_total_assets(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    records = [
        {"timestamp": "2024-01-01T10:00:00", "account": "fund", "changes": {"summary": {}}},
        {"timestamp": "2024-01-02T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10500}}},
    ]
    history_file.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    df = load_portfolio_history(history_file)
    assert len(df) == 1
    assert df["total_assets"].iloc[0] == 10500.0


def test_load_portfolio_history_skips_non_finite_total_assets(tmp_path: Path):
    history_file = tmp_path / "portfolio_history.jsonl"
    records = [
        {"timestamp": "2024-01-01T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": "Infinity"}}},
        {"timestamp": "2024-01-02T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": "NaN"}}},
        {"timestamp": "2024-01-03T10:00:00", "account": "fund", "changes": {"summary": {"total_assets": 10500}}},
    ]
    history_file.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    df = load_portfolio_history(history_file)

    assert len(df) == 1
    assert df["total_assets"].iloc[0] == 10500.0


def test_compute_return_curve_basic():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "total_assets": [10000.0, 10500.0, 10200.0],
        "account": ["fund"] * 3,
    })
    curve = compute_return_curve(df)
    assert len(curve) == 3
    assert curve["cumulative_return_pct"].iloc[0] == 0.0
    assert curve["cumulative_return_pct"].iloc[1] == pytest.approx(5.0)
    assert curve["cumulative_return_pct"].iloc[2] == pytest.approx(2.0)


def test_compute_return_curve_empty():
    assert compute_return_curve(pd.DataFrame()).empty


def test_compute_return_curve_single_row():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"]),
        "total_assets": [10000.0],
        "account": ["fund"],
    })
    assert compute_return_curve(df).empty


def test_compute_return_curve_zero_initial():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "total_assets": [0.0, 100.0],
        "account": ["fund"] * 2,
    })
    assert compute_return_curve(df).empty


def test_compute_return_curve_cleans_string_values_and_bad_timestamps():
    df = pd.DataFrame({
        "timestamp": ["bad timestamp", "2024-01-02", "2024-01-01"],
        "total_assets": ["bad", "110.0", "100.0"],
        "account": ["fund"] * 3,
    })

    curve = compute_return_curve(df)

    assert list(curve["timestamp"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert curve["cumulative_return_pct"].tolist() == pytest.approx([0.0, 10.0])


def test_compute_monthly_returns_basic():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-01", "2024-01-15", "2024-01-31",
            "2024-02-01", "2024-02-15", "2024-02-29",
        ]),
        "total_assets": [10000.0, 10200.0, 10300.0, 10300.0, 10600.0, 10500.0],
        "account": ["fund"] * 6,
    })
    monthly = compute_monthly_returns(df)
    assert len(monthly) == 2
    jan = monthly[monthly["year_month"] == pd.Period("2024-01", freq="M")]
    feb = monthly[monthly["year_month"] == pd.Period("2024-02", freq="M")]
    assert len(jan) == 1
    assert len(feb) == 1
    assert jan["return_pct"].iloc[0] == pytest.approx(3.0)  # (10300 / 10000 - 1) * 100
    assert feb["return_pct"].iloc[0] == pytest.approx(1.9417, rel=1e-3)  # (10500 / 10300 - 1) * 100


def test_compute_monthly_returns_empty():
    assert compute_monthly_returns(pd.DataFrame()).empty


def test_compute_monthly_returns_single_row():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"]),
        "total_assets": [10000.0],
        "account": ["fund"],
    })
    assert compute_monthly_returns(df).empty


def test_compute_monthly_returns_skips_zero_initial_months():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-31", "2024-02-01", "2024-02-29"]),
        "total_assets": [0.0, 100.0, 100.0, 110.0],
        "account": ["fund"] * 4,
    })

    monthly = compute_monthly_returns(df)

    assert list(monthly["year_month"]) == [pd.Period("2024-02", freq="M")]
    assert monthly["return_pct"].iloc[0] == pytest.approx(10.0)


def test_compute_monthly_returns_cleans_bad_rows():
    df = pd.DataFrame({
        "timestamp": ["2024-01-01", "bad timestamp", "2024-01-31"],
        "total_assets": ["100.0", "999.0", "bad"],
        "account": ["fund"] * 3,
    })

    assert compute_monthly_returns(df).empty


def test_compute_risk_metrics_basic():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-01", "2024-01-02", "2024-01-03",
            "2024-01-04", "2024-01-05", "2024-01-06",
        ]),
        "total_assets": [10000.0, 10200.0, 10100.0, 10300.0, 10200.0, 10400.0],
        "account": ["fund"] * 6,
    })
    metrics = compute_risk_metrics(df)
    assert "max_drawdown_pct" in metrics
    assert "annual_volatility_pct" in metrics
    assert "sharpe_ratio" in metrics
    assert metrics["max_drawdown_pct"] <= 0
    assert metrics["annual_volatility_pct"] >= 0


def test_compute_risk_metrics_empty():
    assert compute_risk_metrics(pd.DataFrame()) == {}


def test_compute_risk_metrics_single_row():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"]),
        "total_assets": [10000.0],
        "account": ["fund"],
    })
    assert compute_risk_metrics(df) == {}


def test_compute_risk_metrics_ignores_non_positive_and_bad_values():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "total_assets": [0.0, "bad", 100.0],
        "account": ["fund"] * 3,
    })

    assert compute_risk_metrics(df) == {}


def test_compute_risk_metrics_drawdown():
    # Peak then trough
    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
        ]),
        "total_assets": [10000.0, 11000.0, 10500.0, 9000.0, 9500.0],
        "account": ["fund"] * 5,
    })
    metrics = compute_risk_metrics(df)
    # Max drawdown should be from 11000 to 9000 = -18.18%
    assert metrics["max_drawdown_pct"] == pytest.approx(-18.18, abs=0.01)


def test_build_asset_distribution():
    portfolio = {
        "accounts": {
            "fund": {
                "name": "支付宝基金",
                "positions": [
                    {"name": "易方达中证500", "tag": "wide_index", "market_value": 5000},
                    {"name": "天弘中证人工智能", "tag": "tactical_ai", "market_value": 2000},
                ],
            },
            "stock": {
                "name": "国信证券",
                "positions": [
                    {"name": "半导体", "tag": "semiconductor", "market_value": 1000},
                    {"name": "沃尔核材", "tag": "imported", "market_value": 500},
                ],
            },
        }
    }
    dist = build_asset_distribution(portfolio)
    assert len(dist) == 4
    assert set(dist["account"]) == {"支付宝基金", "国信证券"}
    assert set(dist["tag"]) == {"宽基", "AI战术", "半导体", "未分类"}
    assert dist["market_value"].sum() == 8500.0


def test_build_asset_distribution_empty():
    dist = build_asset_distribution({})
    assert dist.empty


def test_build_asset_distribution_unknown_tag():
    portfolio = {
        "accounts": {
            "fund": {
                "name": "支付宝基金",
                "positions": [
                    {"name": "神秘基金", "tag": "mystery_tag", "market_value": 1000},
                ],
            },
        }
    }
    dist = build_asset_distribution(portfolio)
    assert len(dist) == 1
    assert dist["tag"].iloc[0] == "mystery_tag"


def test_build_asset_distribution_missing_market_value():
    portfolio = {
        "accounts": {
            "fund": {
                "name": "支付宝基金",
                "positions": [
                    {"name": "易方达中证500", "tag": "wide_index"},
                ],
            },
        }
    }
    dist = build_asset_distribution(portfolio)
    assert len(dist) == 1
    assert dist["market_value"].iloc[0] == 0.0


def test_build_asset_distribution_skips_bad_shapes():
    portfolio = {
        "accounts": {
            "bad_account": "not-a-dict",
            "bad_positions": {"name": "坏账户", "positions": "not-a-list"},
            "mixed": {
                "name": "正常账户",
                "positions": [
                    "not-a-position",
                    {"name": "有效持仓", "tag": "wide_index", "market_value": 100},
                ],
            },
        }
    }

    dist = build_asset_distribution(portfolio)

    assert len(dist) == 1
    assert dist["account"].iloc[0] == "正常账户"
    assert dist["name"].iloc[0] == "有效持仓"
    assert dist["market_value"].iloc[0] == 100.0


def test_build_asset_distribution_bad_market_values_become_zero():
    portfolio = {
        "accounts": {
            "fund": {
                "name": "支付宝基金",
                "positions": [
                    {"name": "坏文本", "tag": "wide_index", "market_value": "bad"},
                    {"name": "空值", "tag": "wide_index", "market_value": None},
                    {"name": "NaN", "tag": "wide_index", "market_value": float("nan")},
                ],
            },
        }
    }

    dist = build_asset_distribution(portfolio)

    assert len(dist) == 3
    assert list(dist["market_value"]) == [0.0, 0.0, 0.0]
