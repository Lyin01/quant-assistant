from quant_assistant.importer import _infer_tag


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
