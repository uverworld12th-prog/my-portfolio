import pytest

from lib import db
from lib.common import extract_model, make_sku, normalize_key
from lib.ebay_client import MockEbayClient, PublishNotAllowed, assert_publishable, build_search_filter
from lib.listing_gen import detect_condition, fit_title, generate, translate
from lib.profit import calc_profit, max_buy_price_jpy, shipping_cost_jpy
from lib.source_checker import parse_html


# ---------- 利益計算 ----------
def test_profit_formula(cfg):
    cfg = {**cfg, "profit": {**cfg["profit"], "fee_rate": 0.17, "exchange_rate": 150}}
    r = calc_profit(cfg, 1000, 80000, 5000)
    # 1000 * 0.83 * 150 = 124,500 - 80,000 - 5,000 = 39,500
    assert r.profit_jpy == 39500
    assert r.profit_rate == pytest.approx(39500 / 150000, abs=1e-4)
    assert r.passes


def test_criteria_or_and(cfg):
    p = {**cfg["profit"], "fee_rate": 0.17, "exchange_rate": 150, "min_profit_jpy": 15000, "min_profit_rate": 0.2}
    # 売価 400USD: 受取 49,800, 利益 15,800 / 60,000 = 26% → 両方OK
    # 売価 3000USD: 利益 16,000円 / 450,000 = 3.6% → 額のみOK
    c_or = {**cfg, "profit": {**p, "criteria_mode": "or"}}
    c_and = {**cfg, "profit": {**p, "criteria_mode": "and"}}
    assert calc_profit(c_or, 3000, 373500 - 16000 - 5000, 5000).passes
    assert not calc_profit(c_and, 3000, 373500 - 16000 - 5000, 5000).passes


def test_max_buy_price_roundtrip(cfg):
    for mode in ("or", "and"):
        c = {**cfg, "profit": {**cfg["profit"], "criteria_mode": mode}}
        limit = max_buy_price_jpy(c, 1200, 5800)
        assert calc_profit(c, 1200, limit, 5800).passes
        assert not calc_profit(c, 1200, limit + 5000, 5800).passes


def test_shipping_volumetric(cfg):
    assert shipping_cost_jpy(cfg, 0.4) == 3200
    # 40x30x20/5000 = 4.8kg（容積重量が実重量1kgより大きい）
    assert shipping_cost_jpy(cfg, 1.0, (40, 30, 20)) == 10500
    with pytest.raises(ValueError):
        shipping_cost_jpy(cfg, 50)


# ---------- 出品データ生成 ----------
def test_title_max_80(cfg):
    g = generate({"name_ja": "ニコン Z6II ボディ 極美品 元箱 説明書 付属品完備 " * 3, "brand": "Nikon",
                  "model": "Z6 II", "item_type": "Mirrorless Camera Body Full Frame Professional",
                  "condition_note_ja": "極美品"}, cfg)
    assert len(g.title) <= 80
    assert g.title.startswith("Near Mint Nikon Z6 II")
    assert g.title.endswith("from JAPAN")
    assert "Z6II" not in g.title  # 型番の重複なし
    assert g.condition == "USED_EXCELLENT"
    assert g.item_specifics["Brand"] == ["Nikon"]


def test_fit_title_no_word_cut():
    t = fit_title(["A" * 40, "B" * 30, "verylongword" * 2, "end"], 80)
    assert len(t) <= 80 and "verylongwordverylongword" not in t and t.endswith("end")


def test_translate_reports_untranslated(cfg):
    out, left = translate("美品 謎の語", cfg["glossary"])
    assert "Excellent" in out and "謎の語" in left


def test_condition_priority():
    assert detect_condition("ジャンク 美品")[0] == "FOR_PARTS_OR_NOT_WORKING"
    assert detect_condition("未使用品")[0] == "NEW_OTHER"
    assert detect_condition("")[0] == "USED_GOOD"


def test_extract_model_and_sku():
    assert extract_model("Grand Seiko SBGA211 Snowflake") == "SBGA211"
    assert extract_model("Fujifilm X100V Digital Camera") == "X100V"
    assert extract_model("Nikon Z6 II Mirrorless Camera") == "Z6 II"
    assert extract_model("Canon EOS 5D Mark IV Body") == "5D MARK IV"
    assert extract_model("Leica Summicron 50mm f/2 SUMMICRON50") == "SUMMICRON50"
    assert normalize_key("Z6 II") == "Z6II"
    sku = make_sku("Nikon", "Z6 II", "https://x/1")
    assert sku == make_sku("Nikon", "Z6 II", "https://x/1") and len(sku) <= 50 and sku.startswith("JP-")


# ---------- 安全制約 ----------
@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "PUBLISHED", "ERROR", None])
def test_publish_blocked_unless_approved(status):
    with pytest.raises(PublishNotAllowed):
        assert_publishable({"sku": "X", "status": status})
    with pytest.raises(PublishNotAllowed):
        MockEbayClient().publish_offer("O1", {"sku": "X", "status": status})


def test_publish_allowed_when_approved():
    assert MockEbayClient().publish_offer("O1", {"sku": "X", "status": "APPROVED"}).startswith("MOCKLISTING")


def test_search_filter():
    assert build_search_filter(300, "JP") == "price:[300..],priceCurrency:USD,itemLocationCountry:JP"


# ---------- DB ----------
def test_upsert_does_not_overwrite_approved(tmp_db):
    with db.connect() as c:
        assert db.upsert_draft(c, {"sku": "S1", "title_en": "a"}) == "created"
        assert db.upsert_draft(c, {"sku": "S1", "title_en": "b"}) == "updated"
        db.set_status(c, "S1", "APPROVED")
        assert db.upsert_draft(c, {"sku": "S1", "title_en": "c"}).startswith("skipped")
        assert db.get(c, "S1")["title_en"] == "b"
        with pytest.raises(ValueError):
            db.set_status(c, "S1", "BOGUS")


# ---------- 在庫判定 ----------
KW = ["売り切れ", "SOLD OUT"]


def test_parse_jsonld():
    html = ('<script type="application/ld+json">{"@type":"Product","offers":{"price":"12800",'
            '"availability":"https://schema.org/OutOfStock"}}</script>')
    s = parse_html(html, KW)
    assert s.in_stock is False and s.price_jpy == 12800


def test_parse_keyword_and_unknown():
    assert parse_html("<div>この商品は売り切れです</div>", KW).in_stock is False
    assert parse_html("<div>hello</div>", KW).in_stock is None
