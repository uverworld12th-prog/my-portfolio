"""Phase 3: 承認済み（APPROVED）商品のみ Inventory API で出品公開。

各レコードについて:
  1. PUT  /sell/inventory/v1/inventory_item/{sku}
  2. POST /sell/inventory/v1/offer            （既存Offerがあれば PUT で更新）
  3. POST /sell/inventory/v1/offer/{offerId}/publish
  4. 成功したら DB を PUBLISHED にし offerId / listingId を保存

安全制約: publish 直前に DB を読み直し status == APPROVED を再確認する
（UIで取り消された場合などに備える）。クライアント層でも同じチェックを強制。

例: python scripts/03_publish_ebay.py [--dry-run] [--sku JP-XXXX]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import db  # noqa: E402
from lib.common import banner, setup_logging  # noqa: E402
from lib.config import env, is_mock, load_config  # noqa: E402
from lib.ebay_client import EbayApiError, PublishNotAllowed, get_client  # noqa: E402

POLICY_VARS = ("EBAY_PAYMENT_POLICY_ID", "EBAY_RETURN_POLICY_ID", "EBAY_FULFILLMENT_POLICY_ID")


def validate(rec: dict, cfg: dict) -> list[str]:
    errs = []
    if not rec.get("title_en") or len(rec["title_en"]) > cfg["listing"]["title_max_len"]:
        errs.append(f"タイトルが空または{cfg['listing']['title_max_len']}文字超")
    if not rec.get("image_urls"):
        errs.append("画像URLがありません（最低1枚必要）")
    elif any(not u.startswith("https://") for u in rec["image_urls"]):
        errs.append("画像URLは https:// である必要があります")
    if not rec.get("sell_price_usd") or rec["sell_price_usd"] < cfg["target"]["min_price_usd"]:
        errs.append("売価が対象価格帯未満")
    if not rec.get("category_id"):
        errs.append("category_id 未設定")
    return errs


def inventory_item_payload(rec: dict, cfg: dict) -> dict:
    return {
        "availability": {"shipToLocationAvailability": {"quantity": cfg["listing"]["default_quantity"]}},
        "condition": rec["condition"],
        "product": {
            "title": rec["title_en"],
            "description": rec["description_en"],
            "aspects": rec["item_specifics"],
            "imageUrls": rec["image_urls"],
        },
    }


def offer_payload(rec: dict, cfg: dict) -> dict:
    return {
        "sku": rec["sku"],
        "marketplaceId": env("EBAY_MARKETPLACE_ID", "EBAY_US"),
        "format": "FIXED_PRICE",
        "availableQuantity": cfg["listing"]["default_quantity"],
        "categoryId": rec["category_id"],
        "listingDescription": rec["description_en"],
        "listingPolicies": {
            "paymentPolicyId": env("EBAY_PAYMENT_POLICY_ID", "MOCK_PAYMENT"),
            "returnPolicyId": env("EBAY_RETURN_POLICY_ID", "MOCK_RETURN"),
            "fulfillmentPolicyId": env("EBAY_FULFILLMENT_POLICY_ID", "MOCK_FULFILLMENT"),
        },
        "pricingSummary": {"price": {"value": f"{rec['sell_price_usd']:.2f}",
                                     "currency": cfg["listing"]["currency"]}},
        "merchantLocationKey": env("EBAY_MERCHANT_LOCATION_KEY", "JP_WAREHOUSE_01"),
    }


def publish_one(client, conn, rec: dict, cfg: dict, log) -> bool:
    sku = rec["sku"]
    client.put_inventory_item(sku, inventory_item_payload(rec, cfg))
    log.info("  [1/3] inventory_item 登録 OK")

    payload = offer_payload(rec, cfg)
    existing = client.get_offers(sku)
    if existing:
        offer_id = existing[0]["offerId"]
        client.update_offer(offer_id, {k: v for k, v in payload.items() if k not in ("sku", "marketplaceId", "format")})
        log.info("  [2/3] 既存 offer 更新 OK (%s)", offer_id)
    else:
        offer_id = client.create_offer(payload)
        log.info("  [2/3] offer 作成 OK (%s)", offer_id)
    db.update_fields(conn, sku, offer_id=offer_id)
    conn.commit()

    # --- 安全制約: 公開直前に DB を読み直して APPROVED を再確認 ---
    fresh = db.get(conn, sku)
    listing_id = client.publish_offer(offer_id, fresh)
    log.info("  [3/3] publish OK → listingId=%s", listing_id)
    db.update_fields(conn, sku, listing_id=listing_id, error_message=None)
    db.set_status(conn, sku, "PUBLISHED", f"offerId={offer_id} listingId={listing_id}")
    return True


def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="API を呼ばずに対象とペイロードを表示")
    ap.add_argument("--sku", help="特定 SKU のみ")
    a = ap.parse_args()

    log = setup_logging("publish_ebay")
    banner(log)
    if not is_mock() and not a.dry_run:
        missing = [v for v in POLICY_VARS if not env(v)]
        if missing:
            log.error("Business Policy ID が未設定です: %s", ", ".join(missing))
            return 1

    client = get_client()
    ok = ng = 0
    with db.connect() as conn:
        targets = db.fetch(conn, "APPROVED")
        if a.sku:
            targets = [t for t in targets if t["sku"] == a.sku]
        log.info("APPROVED 対象: %d 件", len(targets))
        for rec in targets:
            log.info("▶ %s  $%.2f  %s", rec["sku"], rec["sell_price_usd"], rec["title_en"])
            errs = validate(rec, cfg)
            if errs:
                ng += 1
                db.update_fields(conn, rec["sku"], error_message=" / ".join(errs))
                log.error("  検証NG: %s", " / ".join(errs))
                continue
            if a.dry_run:
                import json
                print(json.dumps({"inventory_item": inventory_item_payload(rec, cfg),
                                  "offer": offer_payload(rec, cfg)}, ensure_ascii=False, indent=2)[:2000])
                continue
            try:
                publish_one(client, conn, rec, cfg, log)
                ok += 1
            except (EbayApiError, PublishNotAllowed) as e:
                ng += 1
                db.update_fields(conn, rec["sku"], error_message=str(e)[:1000])
                db.log_event(conn, rec["sku"], "PUBLISH_FAILED", str(e)[:1000])
                log.error("  失敗: %s", e)
            conn.commit()
    log.info("完了: 公開 %d 件 / 失敗 %d 件", ok, ng)
    return 0 if ng == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
