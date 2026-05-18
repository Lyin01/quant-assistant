from quant_assistant.importer import _infer_tag, merge_positions


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
