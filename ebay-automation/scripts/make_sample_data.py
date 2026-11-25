"""デモ用サンプルデータを生成（日付は実行日基準）。

- data/research_csv/sample_sold.csv        … Product Research の Sold エクスポート風
- data/candidates/sample_candidates.csv     … 国内仕入れ候補
- data/mock_source_status.json              … EBAY_MOCK=1 時の仕入れ先在庫状況
- data/mock_market.json                     … EBAY_MOCK=1 時の Browse API 疑似相場
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import CANDIDATES_DIR, DATA_DIR, RESEARCH_CSV_DIR  # noqa: E402

PRODUCTS = [  # (タイトル, 中央値USD, 直近90日の販売数)
    ("Nikon Z6 II Mirrorless Camera Body [Near Mint] from JAPAN", 1150, 6),
    ("Leica Summicron-M 50mm f/2 Lens SUMMICRON50 from JAPAN", 1480, 3),
    ("Fujifilm X100V Digital Camera Silver X100V Excellent from Japan", 1390, 9),
    ("Grand Seiko SBGA211 Snowflake Spring Drive Watch from Japan", 4300, 2),
    ("Shimano Stella SW 14000XG Spinning Reel 14000XG Japan", 820, 4),
    ("Canon AE-1 Program 35mm Film Camera Body", 180, 12),   # 300USD未満 → 除外
    ("Olympus OM-1 Film Camera OM1 Body", 260, 1),           # 回数不足 → 除外
]

CANDIDATES = [
    dict(name_ja="ニコン Z6II ボディ 極美品 元箱 説明書 付属品完備", brand="Nikon", model="Z6 II",
         item_type="Mirrorless Camera Body", price_jpy="98000", condition_note_ja="極美品 動作確認済み キズなし カビなし",
         url="https://example.jp/item/nikon-z6ii-001", weight_kg="1.2", dims_cm="25x18x15",
         category_id="31388", sell_price_usd="", aspects="Series:Nikon Z;Mount:Nikon Z;Sensor Size:Full Frame"),
    dict(name_ja="富士フイルム X100V シルバー 美品 箱付き", brand="Fujifilm", model="X100V",
         item_type="Digital Camera", price_jpy="128000", condition_note_ja="美品 小スレあり 動作品",
         url="https://example.jp/item/fuji-x100v-002", weight_kg="0.9", dims_cm="20x15x12",
         category_id="31388", sell_price_usd="", aspects="Color:Silver"),
    dict(name_ja="グランドセイコー SBGA211 雪白 スプリングドライブ 腕時計", brand="Grand Seiko", model="SBGA211",
         item_type="Watch", price_jpy="480000", condition_note_ja="美品 箱付き 保証書あり",
         url="https://example.jp/item/gs-sbga211-003", weight_kg="0.6", dims_cm="15x12x10",
         category_id="31387", sell_price_usd="", aspects="Movement:Spring Drive;Case Material:Titanium"),
    dict(name_ja="シマノ ステラ SW 14000XG リール 中古", brand="Shimano", model="14000XG",
         item_type="Spinning Reel", price_jpy="99000", condition_note_ja="中古 傷あり 動作品",
         url="https://example.jp/item/stella-sw-004", weight_kg="1.5", dims_cm="25x20x15",
         category_id="36147", sell_price_usd="", aspects="Model:Stella SW 14000XG"),
]

MOCK_SOURCE = {  # 監視デモ: 1件は売切れ、1件は値上がり
    "https://example.jp/item/fuji-x100v-002": {"in_stock": False, "price_jpy": 128000},
    "https://example.jp/item/nikon-z6ii-001": {"in_stock": True, "price_jpy": 135000},
}


def main() -> None:
    rnd = random.Random(42)
    today = datetime.now()
    RESEARCH_CSV_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESEARCH_CSV_DIR / "sample_sold.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Listing title", "Avg sold price", "Total sold", "Date last sold"])
        for title, median, n in PRODUCTS:
            for _ in range(n):
                d = today - timedelta(days=rnd.randint(1, 85))
                w.writerow([title, f"${median * rnd.uniform(0.9, 1.1):,.2f}", 1, d.strftime("%Y-%m-%d")])
            # 期間外（120日前）の古いデータ → 集計対象外
            w.writerow([title, f"${median:,.2f}", 5, (today - timedelta(days=120)).strftime("%Y-%m-%d")])
    images = "https://placehold.co/800x600.jpg?text={}"
    with open(CANDIDATES_DIR / "sample_candidates.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[*CANDIDATES[0].keys(), "image_urls"])
        w.writeheader()
        for c in CANDIDATES:
            w.writerow({**c, "image_urls": "|".join(images.format(f"{c['model'].replace(' ', '')}-{i}") for i in (1, 2))})
    (DATA_DIR / "mock_source_status.json").write_text(json.dumps(MOCK_SOURCE, indent=2), encoding="utf-8")
    from lib.common import extract_model, normalize_key
    mock_market = {normalize_key(extract_model(t)): m for t, m, _ in PRODUCTS}
    (DATA_DIR / "mock_market.json").write_text(json.dumps(mock_market, indent=2), encoding="utf-8")
    print("サンプルデータを生成しました:")
    for p in (RESEARCH_CSV_DIR / "sample_sold.csv", CANDIDATES_DIR / "sample_candidates.csv",
              DATA_DIR / "mock_source_status.json", DATA_DIR / "mock_market.json"):
        print("  ", p.relative_to(DATA_DIR.parent))


if __name__ == "__main__":
    main()
