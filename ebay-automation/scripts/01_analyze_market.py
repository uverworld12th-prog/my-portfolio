"""Phase 2-1: 市場分析。

1. data/research_csv/*.csv（Seller Hub > Product Research の Sold エクスポート）を読み込み
2. 直近 N 日で複数回売れている型番・キーワードを抽出
3. Browse API で現在のライバル最安値・出品数を照合
4. 想定売価・国際送料から「仕入れ上限額（円）」を算出して CSV 出力

CSV列名は表記ゆれに対応（下記 COLUMN_ALIASES）。`keyword` 列があればそれでグルーピングし、
なければタイトルから型番を自動抽出する。

将来、外部 Sold データ API に切り替える場合は SoldDataSource を実装して差し替える。

例: python scripts/01_analyze_market.py [--as-of 2026-11-25] [--no-browse]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import banner, extract_model, normalize_key, setup_logging  # noqa: E402
from lib.config import OUTPUT_DIR, RESEARCH_CSV_DIR, load_config  # noqa: E402
from lib.ebay_client import get_client  # noqa: E402
from lib.profit import max_buy_price_jpy, shipping_cost_jpy, suggest_sell_price_usd  # noqa: E402

COLUMN_ALIASES = {
    "title": ["title", "listing title", "listing", "item title", "タイトル", "商品名"],
    "price": ["avg sold price", "sold price", "price", "average sold price", "平均落札価格", "落札価格", "価格"],
    "sold_count": ["total sold", "quantity sold", "sold", "販売数", "落札数"],
    "date": ["date last sold", "last sold", "sold date", "date", "最終販売日", "落札日"],
    "keyword": ["keyword", "model", "型番", "キーワード"],
}


class SoldDataSource(Protocol):
    def load(self) -> pd.DataFrame: ...


def _norm(s: str) -> str:
    return str(s).strip().lower().replace("_", " ")


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")


class SellerHubCsvSource:
    """Seller Hub Product Research の CSV を正規化して読み込む。"""

    def __init__(self, folder: Path):
        self.folder = folder

    def load(self) -> pd.DataFrame:
        frames = []
        for f in sorted(self.folder.glob("*.csv")):
            df = pd.read_csv(f, encoding="utf-8-sig")
            cols = {_norm(c): c for c in df.columns}
            rename = {}
            for std, aliases in COLUMN_ALIASES.items():
                for al in aliases:
                    if al in cols:
                        rename[cols[al]] = std
                        break
            df = df.rename(columns=rename)
            if "title" not in df or "price" not in df:
                print(f"  ! {f.name}: title/price 列が見つからないためスキップ (列: {list(df.columns)})")
                continue
            df["price"] = _to_number(df["price"])
            df["sold_count"] = _to_number(df["sold_count"]).fillna(1) if "sold_count" in df else 1
            df["date"] = pd.to_datetime(df["date"], errors="coerce") if "date" in df else pd.NaT
            if "keyword" not in df:
                df["keyword"] = None
            df["source_file"] = f.name
            frames.append(df[["title", "price", "sold_count", "date", "keyword", "source_file"]])
        if not frames:
            return pd.DataFrame(columns=["title", "price", "sold_count", "date", "keyword", "source_file"])
        return pd.concat(frames, ignore_index=True)


def aggregate(df: pd.DataFrame, cfg: dict, as_of: datetime) -> pd.DataFrame:
    r = cfg["research"]
    since = as_of - timedelta(days=r["lookback_days"])
    df = df.copy()
    df = df[df["date"].isna() | ((df["date"] >= since) & (df["date"] <= as_of))]
    df["key"] = df["keyword"].where(df["keyword"].notna() & (df["keyword"].astype(str).str.strip() != ""),
                                    df["title"].map(extract_model))
    df = df.dropna(subset=["key", "price"])
    df["key"] = df["key"].astype(str).str.strip().str.upper()
    g = df.groupby("key").agg(
        sold_count=("sold_count", "sum"),
        sold_median_usd=("price", "median"),
        sold_min_usd=("price", "min"),
        sold_max_usd=("price", "max"),
        sample_title=("title", "first"),
        last_sold=("date", "max"),
    ).reset_index()
    g = g[(g["sold_count"] >= r["min_sold_count"]) & (g["sold_median_usd"] >= cfg["target"]["min_price_usd"])]
    return g.sort_values(["sold_count", "sold_median_usd"], ascending=False).reset_index(drop=True)


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", type=Path, default=RESEARCH_CSV_DIR)
    ap.add_argument("--as-of", help="基準日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--no-browse", action="store_true", help="Browse API照合をスキップ")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    log = setup_logging("analyze_market")
    banner(log)
    as_of = datetime.fromisoformat(a.as_of) if a.as_of else datetime.now()
    raw = SellerHubCsvSource(a.csv_dir).load()
    log.info("CSV読込 %d 行 (%s)", len(raw), a.csv_dir)
    agg = aggregate(raw, cfg, as_of)
    log.info("直近%d日で%d回以上・%sUSD以上: %d キーワード",
             cfg["research"]["lookback_days"], cfg["research"]["min_sold_count"],
             cfg["target"]["min_price_usd"], len(agg))
    if agg.empty:
        return 0

    client = None if a.no_browse else get_client()
    ship = shipping_cost_jpy(cfg)
    rows = []
    for _, r in agg.iterrows():
        rival_count, rival_min = None, None
        if client:
            try:
                res = client.search_items(r["key"], cfg["target"]["min_price_usd"],
                                          cfg["target"]["item_location_country"], limit=50)
                prices = [float(i["price"]["value"]) for i in res.get("itemSummaries", []) if i.get("price")]
                # ジャンク・付属品のみ等の外れ値（落札中央値 × ratio 未満）は最安値計算から除外
                floor = r["sold_median_usd"] * cfg["research"].get("rival_outlier_ratio", 0)
                valid = [p for p in prices if p >= floor]
                rival_count = res.get("total", len(prices))
                rival_min = min(valid) if valid else None
            except Exception as e:  # noqa: BLE001
                log.warning("Browse API失敗 %s: %s", r["key"], e)
        sell = suggest_sell_price_usd(cfg, rival_min, r["sold_median_usd"])
        rows.append({
            **r.to_dict(),
            "match_key": normalize_key(r["key"]),
            "rival_count_jp": rival_count,
            "rival_min_usd": rival_min,
            "target_sell_usd": sell,
            "est_ship_jpy": ship,
            "max_buy_jpy": max_buy_price_jpy(cfg, sell, ship) if sell else None,
        })
    out_df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = a.out or OUTPUT_DIR / f"market_analysis_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out_df.to_csv(out, index=False, encoding="utf-8-sig")
    # 02_create_draft.py が参照する最新版
    out_df.to_csv(OUTPUT_DIR / "market_analysis_latest.csv", index=False, encoding="utf-8-sig")
    log.info("出力 → %s", out)
    show = out_df[["key", "sold_count", "sold_median_usd", "rival_count_jp", "rival_min_usd",
                   "target_sell_usd", "max_buy_jpy"]]
    print(show.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
