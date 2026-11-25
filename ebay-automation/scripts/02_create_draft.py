"""Phase 2-2: 下書き生成。

data/candidates/*.csv（国内仕入れ候補）から英語出品データを生成し、利益計算のうえ
SQLite（data/drafts.db）へ PENDING で保存する。

候補CSVの列:
  name_ja, brand, model, item_type, price_jpy, condition_note_ja, url,
  image_urls (| 区切り), weight_kg, dims_cm (例 20x15x12), category_id,
  sell_price_usd (任意: 空なら market_analysis_latest.csv の target_sell_usd を型番で引く),
  market_key (任意: 市場分析のキーが model と異なる場合に指定),
  aspects (任意: "Mount:Nikon F;Focal Length:50mm")

例: python scripts/02_create_draft.py [--input path.csv] [--include-unprofitable]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import db  # noqa: E402
from lib.common import banner, make_sku, normalize_key, setup_logging  # noqa: E402
from lib.config import CANDIDATES_DIR, OUTPUT_DIR, load_config  # noqa: E402
from lib.listing_gen import generate  # noqa: E402
from lib.profit import calc_profit, shipping_cost_jpy  # noqa: E402


def _f(v):
    try:
        return None if v is None or pd.isna(v) or str(v).strip() == "" else float(v)
    except (TypeError, ValueError):
        return None


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def load_market_prices() -> dict[str, float]:
    p = OUTPUT_DIR / "market_analysis_latest.csv"
    if not p.exists():
        return {}
    df = pd.read_csv(p, encoding="utf-8-sig")
    return {normalize_key(str(k)): float(v) for k, v in zip(df["key"], df["target_sell_usd"]) if pd.notna(v)}


def parse_dims(s: str):
    try:
        parts = [float(x) for x in s.lower().replace("×", "x").split("x")]
        return tuple(parts) if len(parts) == 3 else None
    except ValueError:
        return None


def build_record(c: dict, cfg: dict, market: dict[str, float]) -> tuple[dict | None, str]:
    url = _s(c.get("url"))
    price_jpy = _f(c.get("price_jpy"))
    if not url or price_jpy is None:
        return None, "url または price_jpy が空"
    key = normalize_key(_s(c.get("market_key")) or _s(c.get("model")))
    sell = _f(c.get("sell_price_usd")) or market.get(key)
    if not sell:
        return None, "想定売価が不明（sell_price_usd 未入力 & 市場分析に型番なし）"
    if sell < cfg["target"]["min_price_usd"]:
        return None, f"売価 {sell} USD が対象価格帯未満"

    ship = shipping_cost_jpy(cfg, _f(c.get("weight_kg")), parse_dims(_s(c.get("dims_cm"))))
    pr = calc_profit(cfg, sell, price_jpy, ship)
    gen = generate({k: _s(v) for k, v in c.items()}, cfg)
    images = [u.strip() for u in _s(c.get("image_urls")).split("|") if u.strip()]
    rec = {
        "sku": make_sku(_s(c.get("brand")), _s(c.get("model")), url),
        "source_name_ja": _s(c.get("name_ja")),
        "source_url": url,
        "source_price_jpy": int(price_jpy),
        "last_source_price_jpy": int(price_jpy),
        "condition_note_ja": _s(c.get("condition_note_ja")),
        "title_en": gen.title,
        "description_en": gen.description,
        "item_specifics": gen.item_specifics,
        "image_urls": images,
        "condition": gen.condition,
        "category_id": _s(c.get("category_id")) or cfg["listing"]["default_category_id"],
        "sell_price_usd": sell,
        "ship_cost_jpy": ship,
        "expected_profit_jpy": pr.profit_jpy,
        "expected_profit_rate": pr.profit_rate,
        "review_note": ("未翻訳語: " + ", ".join(gen.untranslated)) if gen.untranslated else None,
    }
    if not pr.passes:
        return rec, f"利益基準未達 (利益 {pr.profit_jpy:,}円 / {pr.profit_rate:.1%})"
    return rec, "ok"


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, nargs="*")
    ap.add_argument("--include-unprofitable", action="store_true", help="利益基準未達もPENDING登録する")
    a = ap.parse_args()

    log = setup_logging("create_draft")
    banner(log)
    files = a.input or sorted(CANDIDATES_DIR.glob("*.csv"))
    if not files:
        log.error("候補CSVがありません: %s", CANDIDATES_DIR)
        return 1
    market = load_market_prices()
    stats = {"created": 0, "updated": 0, "skipped": 0}
    with db.connect() as conn:
        for f in files:
            for c in pd.read_csv(f, encoding="utf-8-sig", dtype=str).to_dict("records"):
                rec, reason = build_record(c, cfg, market)
                label = _s(c.get("name_ja"))[:30]
                if rec is None or (reason != "ok" and not a.include_unprofitable):
                    stats["skipped"] += 1
                    log.info("SKIP  %-30s : %s", label, reason)
                    continue
                result = db.upsert_draft(conn, rec)
                key = result.split()[0] if result.split()[0] in stats else "skipped"
                stats[key] += 1
                log.info("%-7s %s 売価$%.2f 利益%s円(%.1f%%) %s | %s",
                         result.upper(), rec["sku"], rec["sell_price_usd"],
                         f"{rec['expected_profit_jpy']:,}", rec["expected_profit_rate"] * 100,
                         "" if reason == "ok" else f"[{reason}]", rec["title_en"])
    log.info("完了: 新規 %(created)d / 更新 %(updated)d / スキップ %(skipped)d", stats)
    log.info("→ 承認UI: streamlit run app_review.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
