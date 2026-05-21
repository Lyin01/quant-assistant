from quant_assistant.importer import (
    _ocr_import_error_message,
    _infer_market_proxy,
    _infer_tag,
    merge_positions,
    parse_ocr_import_text,
    recalc_account_summary,
    update_account_from_import,
)


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


def test_ocr_import_error_message_for_python_313_plus(monkeypatch):
    monkeypatch.setattr("quant_assistant.importer.sys.version_info", (3, 13, 0))
    assert "Python 3.13" in _ocr_import_error_message()
    assert "3.12" in _ocr_import_error_message()


def test_ocr_import_error_message_includes_original_exception(monkeypatch):
    monkeypatch.setattr("quant_assistant.importer.sys.version_info", (3, 12, 9))
    message = _ocr_import_error_message(ImportError("libGL.so.1: cannot open shared object file"))
    assert "原始导入错误" in message
    assert "libGL.so.1" in message


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
    updated = recalc_account_summary(account, "fund")
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
    updated = recalc_account_summary(account, "stock")
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
    updated = recalc_account_summary(account, "stock")
    assert updated["today_pnl"] == -40.0
    assert updated["holding_pnl"] == -15.22
    assert updated["available_cash"] == 1000.0
    assert updated["total_assets"] == 1500.0


def test_recalc_fund_ignores_available_cash():
    """基金账户即使有 available_cash 字段也不应计入 total_assets。"""
    account = {
        "name": "支付宝基金",
        "total_assets": 0.0,
        "available_cash": 5000.0,  # 可能被 merge_account_summary 误加入
        "positions": [
            {"name": "A", "market_value": 1000.0},
        ],
    }
    updated = recalc_account_summary(account, "fund")
    assert updated["total_assets"] == 1000.0


def test_infer_market_proxy_from_name():
    assert _infer_market_proxy("易方达中证500", "wide_index") == "中证500"
    assert _infer_market_proxy("华宝纳斯达克精选", "overseas") == "纳指"
    assert _infer_market_proxy("博时标普500ETF联接", "overseas") == "标普500"
    assert _infer_market_proxy("广发中证军工ETF联接", "military") == "军工"
    assert _infer_market_proxy("天弘中证电网设备", "power_grid") == "电网设备"
    assert _infer_market_proxy("某个不认识的基金", "imported") is None


def test_merge_positions_infers_market_proxy_for_new_holdings():
    """新持仓应自动推断 market_proxy。"""
    existing = [{"name": "半导体", "tag": "semiconductor", "market_value": 203.5}]
    imported = [{"name": "易方达中证500", "tag": "wide_index", "market_value": 5594.65}]

    merged = merge_positions(existing, imported)

    assert len(merged) == 2
    new_pos = next(p for p in merged if p["name"] == "易方达中证500")
    assert new_pos["market_proxy"] == "中证500"


def test_update_account_from_import_preserves_ocr_summary_totals():
    """截图摘要总资产比 OCR 明细更权威，不能被明细合计覆盖。"""
    account = {
        "name": "支付宝基金",
        "total_assets": 0.0,
        "today_pnl": 0.0,
        "positions": [],
    }
    imported = [
        {"name": "易方达中证500", "tag": "wide_index", "market_value": 5594.65},
        {"name": "天弘中证电网设备", "tag": "power_grid", "market_value": 3270.40},
    ]
    summary = {
        "total_assets": 18118.73,
        "today_pnl": -228.25,
    }

    updated = update_account_from_import(account, imported, "fund", summary)

    assert updated["total_assets"] == 18118.73
    assert updated["today_pnl"] == -228.25
    assert len(updated["positions"]) == 2


def test_update_account_from_import_recalculates_when_summary_is_missing():
    account = {
        "name": "国信证券",
        "total_assets": 0.0,
        "available_cash": 1000.0,
        "positions": [],
    }
    imported = [
        {"name": "半导体", "tag": "semiconductor", "market_value": 203.5},
        {"name": "沃尔核材", "tag": "imported", "market_value": 2249.0},
    ]

    updated = update_account_from_import(account, imported, "stock")

    assert updated["market_value"] == 2452.5
    assert updated["total_assets"] == 3452.5


def test_parse_ocr_import_text_keeps_account_summary_separate_from_positions():
    text = """
    基金资产: 17869.32
    当日收益: 126.19
    示例基金 | 126.19 | +0.10% | +1.00 | +0.80%
    """

    parsed, summary, positions = parse_ocr_import_text(text)

    assert summary["total_assets"] == 17869.32
    assert summary["today_pnl"] == 126.19
    assert parsed.loc[0, "market_value"] == 126.19
    assert positions[0]["name"] == "示例基金"


def test_parse_stock_screenshot_multiline_ocr():
    text = """
    总资产(元）>
    今日盈亏》
    持仓盈亏
    9,703.93
    -141.15
    -156.37
    总市值
    可用
    转账
    9,681.90
    22.03
    名称/市值=
    持股/可卖=
    现价/成本=
    持仓盈亏
    沃尔核材
    100
    21.760
    -124.02
    2,176.00
    100
    23.000
    -5.39%
    通宇通讯
    100
    51.640
    -58.25
    5,164.00
    52.223
    -1.12%
    纳指大成
    900
    1.719
    -5.00
    1,547.10
    900
    1.725
    -0.32%
    创新药
    300
    0.784
    -12.20
    300
    0.825
    235.20
    -4.93%
    半导体
    100
    2.077
    +0.60
    207.70
    100
    2.071
    +0.29%
    机器人
    300
    1.173
    +42.50
    351.90
    300
    1.031
    +13.74%
    证券服务由国信证券提供，客服电话95536
    自选
    行情
    """

    parsed, summary, positions = parse_ocr_import_text(text)

    assert summary["total_assets"] == 9703.93
    assert summary["today_pnl"] == -141.15
    assert summary["holding_pnl"] == -156.37
    assert summary["market_value"] == 9681.90
    assert summary["available_cash"] == 22.03
    assert list(parsed["name"]) == ["沃尔核材", "通宇通讯", "纳指大成", "创新药", "半导体", "机器人"]

    walter = next(item for item in positions if item["name"] == "沃尔核材")
    assert walter["market_value"] == 2176.0
    assert walter["shares"] == 100
    assert walter["price"] == 21.76
    assert walter["cost"] == 23.0
    assert walter["holding_pnl"] == -124.02
    assert walter["holding_pnl_pct"] == -5.39

    innovative_drug = next(item for item in positions if item["name"] == "创新药")
    assert innovative_drug["market_value"] == 235.2
    assert innovative_drug["price"] == 0.784
    assert innovative_drug["cost"] == 0.825


def test_parse_fund_screenshot_multiline_ocr():
    text = """
    账户资产
    二 场内穿透
    17.869.32
    +11.95
    关联板块
    当日收益
    持有收益
    05-18
    05-18
    05-18
    易方达中证500··
    +0.22%
    -161.14
    中证500指数
    ￥ 5510.16
    -2.84%
    天弘中证人工
    +0.87%
    +50.16
    ￥450.16
    中证人工智能
    +12.54%
    大成纳斯达克1··
    -1.54%
    +59.95
    ￥2059.95 05-15
    纳斯达克100
    +3.00%
    易方达稳健收·
    -0.06%
    -1.21
    混债
    ￥ 398.79
    -0.30%
    博时标普500E··
    -1.24%
    +9.18
    ￥ 109.18 05-15
    标普500
    +9.18%
    广发中证军工E·
    -0.07%
    -124.95
    ￥ 1345.14
    中证军工
    -8.50%
    华宝纳斯达克··
    -1.33%
    +269.53
    ￥3145.75 05-15
    纳斯达克精选
    +9.37%
    """

    parsed, summary, positions = parse_ocr_import_text(text)

    assert summary["total_assets"] == 17869.32
    assert summary["today_pnl"] == 11.95
    assert summary["holding_pnl"] is None
    assert list(parsed["name"]) == [
        "易方达中证500",
        "天弘中证人工",
        "大成纳斯达克1",
        "易方达稳健收",
        "博时标普500E",
        "广发中证军工E",
        "华宝纳斯达克",
    ]

    midcap = next(item for item in positions if item["name"] == "易方达中证500")
    assert midcap["market_value"] == 5510.16
    assert midcap["last_daily_pct"] == 0.22
    assert midcap["holding_pnl"] == -161.14
    assert midcap["holding_pnl_pct"] == -2.84
    assert midcap["market_proxy"] == "中证500"


def test_update_account_from_import_stock_uses_summary_total_not_mixed_position_sum():
    account = {
        "name": "国信证券",
        "total_assets": 0.0,
        "available_cash": 0.0,
        "positions": [],
    }
    imported = [
        {"name": "股票A", "tag": "imported", "market_value": 21381.99},
    ]
    summary = {
        "total_assets": 9703.93,
        "market_value": 9000.00,
        "available_cash": 703.93,
    }

    updated = update_account_from_import(account, imported, "stock", summary)

    assert updated["total_assets"] == 9703.93
    assert updated["market_value"] == 9000.00
    assert updated["available_cash"] == 703.93
