"""Phase 4: 在庫・価格監視。

PUBLISHED の商品について仕入れ先の在庫・価格をチェックし、
  - 売り切れ、または
  - 値上がりで利益基準を割った
場合に bulk_update_price_quantity で eBay 在庫を 0 にし、ステータスを OUT_OF_STOCK に変更、
ログと通知（NOTIFY_WEBHOOK_URL）を出す。判定不能（取得失敗等）の場合は安全側に倒さず警告のみ。
→ 判定不能が連続する場合に在庫0にしたい場合は --zero-on-unknown を付ける。

cron 例（1時間おき）:
  0 * * * * cd /path/to/ebay-automation && .venv/bin/python scripts/04_stock_monitor.py >> logs/cron.log 2>&1

例: python scripts/04_stock_monitor.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import db  # noqa: E402
from lib.common import banner, setup_logging  # noqa: E402
from lib.config import env, is_mock, load_config  # noqa: E402
from lib.ebay_client import get_client  # noqa: E402
from lib.profit import calc_profit  # noqa: E402
from lib.source_checker import check  # noqa: E402


def notify(msg: str, log) -> None:
    url = env("NOTIFY_WEBHOOK_URL")
    if not url or is_mock():
        return
    try:
        # Slack は "text"、Discord は "content" を読む
        requests.post(url, json={"text": msg, "content": msg}, timeout=10)
    except requests.RequestException as e:
        log.warning("通知失敗: %s", e)


def decide(rec: dict, st, cfg: dict, zero_on_unknown: bool) -> tuple[bool, str]:
    if st.in_stock is False:
        return True, f"仕入れ先売切れ ({st.reason})"
    if st.price_jpy and st.price_jpy != rec["source_price_jpy"]:
        pr = calc_profit(cfg, rec["sell_price_usd"], st.price_jpy, rec["ship_cost_jpy"])
        if not pr.passes:
            return True, (f"値上がりで利益基準割れ {rec['source_price_jpy']:,}→{st.price_jpy:,}円 "
                          f"(利益 {pr.profit_jpy:,}円 / {pr.profit_rate:.1%})")
    if st.in_stock is None and zero_on_unknown:
        return True, f"在庫判定不能 ({st.reason})"
    return False, ""


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--zero-on-unknown", action="store_true")
    a = ap.parse_args()

    log = setup_logging("stock_monitor")
    banner(log)
    client = get_client()
    interval = 0 if is_mock() else cfg["monitor"]["request_interval_sec"]
    with db.connect() as conn:
        recs = db.fetch(conn, "PUBLISHED")
        log.info("監視対象 PUBLISHED: %d 件", len(recs))
        to_zero: list[tuple[dict, str]] = []
        for i, rec in enumerate(recs):
            if i and interval:
                time.sleep(interval)
            st = check(rec["source_url"], cfg)
            db.update_fields(conn, rec["sku"], last_checked_at=db.now(),
                             **({"last_source_price_jpy": st.price_jpy} if st.price_jpy else {}))
            stop, why = decide(rec, st, cfg, a.zero_on_unknown)
            mark = "STOP" if stop else ("WARN" if st.in_stock is None else " OK ")
            log.info("[%s] %s 在庫=%s 価格=%s (%s)", mark, rec["sku"], st.in_stock, st.price_jpy, st.reason)
            if stop:
                to_zero.append((rec, why))
        if not to_zero:
            log.info("在庫0更新が必要な商品はありません")
            return 0
        if a.dry_run:
            for rec, why in to_zero:
                log.info("(dry-run) 在庫0予定: %s — %s", rec["sku"], why)
            return 0
        reqs = [{"sku": r["sku"],
                 "shipToLocationAvailability": {"quantity": 0},
                 "offers": [{"offerId": r["offer_id"], "availableQuantity": 0}] if r.get("offer_id") else []}
                for r, _ in to_zero]
        # API 上限は 1 リクエスト 25 件
        results = []
        for k in range(0, len(reqs), 25):
            results += client.bulk_update_price_quantity(reqs[k:k + 25])
        status_by_sku = {r.get("sku"): r.get("statusCode") for r in results}
        for rec, why in to_zero:
            code = status_by_sku.get(rec["sku"])
            if code == 200:
                db.set_status(conn, rec["sku"], "OUT_OF_STOCK", why)
                msg = f"🛑 eBay在庫を0に更新: {rec['sku']} {rec['title_en']}\n理由: {why}\n仕入れ先: {rec['source_url']}"
                log.warning(msg.replace("\n", " | "))
                notify(msg, log)
            else:
                db.log_event(conn, rec["sku"], "ZERO_QTY_FAILED", f"status={code} {why}")
                log.error("在庫0更新失敗 %s status=%s", rec["sku"], code)
                notify(f"⚠ 在庫0更新に失敗: {rec['sku']} (status={code}) 手動で確認してください", log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
