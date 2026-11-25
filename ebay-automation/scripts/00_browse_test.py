"""Phase 1: Browse API 疎通確認。

「価格 300 USD 以上・発送元 Japan」の現在出品中（Active）商品を検索し CSV 出力する。
※ Browse API は Active のみ。落札（Sold）データは Seller Hub の CSV を使うこと。

例: python scripts/00_browse_test.py "nikon lens" --limit 50
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import banner, setup_logging  # noqa: E402
from lib.config import OUTPUT_DIR, load_config  # noqa: E402
from lib.ebay_client import get_client  # noqa: E402


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--min-price", type=float, default=cfg["target"]["min_price_usd"])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    log = setup_logging("browse_test")
    banner(log)
    res = get_client().search_items(a.query, a.min_price, cfg["target"]["item_location_country"], a.limit)
    rows = [{
        "item_id": it.get("itemId"),
        "title": it.get("title"),
        "price_usd": float(it.get("price", {}).get("value", 0)),
        "currency": it.get("price", {}).get("currency"),
        "condition": it.get("condition"),
        "seller": (it.get("seller") or {}).get("username"),
        "url": it.get("itemWebUrl"),
    } for it in res.get("itemSummaries", [])]
    df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = a.out or OUTPUT_DIR / f"browse_{datetime.now():%Y%m%d_%H%M%S}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    log.info("総ヒット数 %s 件 / 取得 %d 件 → %s", res.get("total", 0), len(df), out)
    if not df.empty:
        print(df[["price_usd", "condition", "title"]].head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
