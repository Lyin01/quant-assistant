from quant_assistant.importer import _infer_tag, merge_positions, recalc_account_summary


def test_infer_tag_wide_index():
    assert _infer_tag("易方达中证500") == "wide_index"
    assert _infer_tag("华夏沪深300ETF") == "wide_index"
    assert _infer_tag("中证A500指数") == "wide_index"


def test_infer_tag_overseas():
    assert _infer_tag("华宝纳斯达克精选") == "overseas"
    assert _infer_tag("博时标普500ETF联接") == "overseas"
    assert _infer_tag("大成纳斯达克100") == "overseas"
    assert _infer_tag("纳指大成") == "overseas"


def test_infer_tag_tactical_ai():
    assert _infer_tag("天弘中证人工智能") == "tactical_ai"


def test_infer_tag_healthcare():
    assert _infer_tag("广发中证创新药ETF") == "healthcare"
    assert _infer_tag("易方达创新药") == "healthcare"


def test_infer_tag_defensive():
    assert _infer_tag("易方达稳健收益") == "defensive"


def test_infer_tag_unknown_returns_imported():
    assert _infer_tag("沃尔核材") == "imported"
    assert _infer_tag("某个不认识的基金") == "imported"


def test_merge_positions_preserves_existing_fields_when_import_is_partial():
    """导入数据缺少某些字段时，应保留现有持仓的对应字段。"""
    existing = [
        {
            "id": "semi_old",
            "name": "半导体",
            "tag": "semiconductor",
            "market_value": 203.5,
            "holding_pnl_pct": -1.74,
            "shares": 100,
            "price": 2.035,
            "cost": 2.071,
            "market_proxy": "半导体",
        }
    ]
    # 导入数据只更新了股数，缺少市值等其他字段
    imported = [{"name": "半导体", "shares": 200}]

    merged = merge_positions(existing, imported)

    assert len(merged) == 1
    assert merged[0]["shares"] == 200
    assert merged[0]["market_value"] == 203.5
    assert merged[0]["holding_pnl_pct"] == -1.74
    assert merged[0]["price"] == 2.035
    assert merged[0]["cost"] == 2.071
    assert merged[0]["market_proxy"] == "半导体"
    assert merged[0]["id"] == "semi_old"


def test_merge_positions_uses_import_value_when_present():
    """导入数据明确提供了字段值时，应覆盖现有值。"""
    existing = [
        {
            "name": "半导体",
            "tag": "semiconductor",
            "market_value": 203.5,
            "shares": 100,
        }
    ]
    imported = [{"name": "半导体", "market_value": 250.0, "shares": 150}]

    merged = merge_positions(existing, imported)

    assert len(merged) == 1
    assert merged[0]["market_value"] == 250.0
    assert merged[0]["shares"] == 150


def test_recalc_fund_account_summary():
    """基金账户：total_assets = 各持仓市值之和。"""
    account = {
        "name": "支付宝基金",
        "total_assets": 0.0,
        "positions": [
            {"name": "A", "market_value": 1000.0},
            {"name": "B", "market_value": 2500.5},
            {"name": "C", "market_value": 0.0},
        ],
    }
    updated = recalc_account_summary(account)
    assert updated["total_assets"] == 3500.5


def test_recalc_stock_account_summary():
    """股票账户：total_assets = 持仓市值之和 + available_cash。"""
    account = {
        "name": "国信证券",
        "total_assets": 0.0,
        "market_value": 0.0,
        "available_cash": 1644.28,
        "positions": [
            {"name": "半导体", "market_value": 203.5},
            {"name": "沃尔核材", "market_value": 2249.0},
        ],
    }
    updated = recalc_account_summary(account)
    assert updated["market_value"] == 2452.5
    assert updated["total_assets"] == 4096.78


def test_recalc_account_preserves_existing_fields():
    """重新计算时保留原有非计算字段。"""
    account = {
        "name": "国信证券",
        "total_assets": 9999.0,
        "today_pnl": -40.0,
        "holding_pnl": -15.22,
        "available_cash": 1000.0,
        "positions": [{"name": "半导体", "market_value": 500.0}],
    }
    updated = recalc_account_summary(account)
    assert updated["today_pnl"] == -40.0
    assert updated["holding_pnl"] == -15.22
    assert updated["available_cash"] == 1000.0
    assert updated["total_assets"] == 1500.0
