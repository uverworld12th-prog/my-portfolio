# CLAUDE.md — eBay 高額商品・半自動出品システム 開発ルール

## 絶対ルール（ガードレール）
1. **スクレイピング禁止**: eBay のデータ取得・出品操作は公式 API（Browse API / Inventory API）のみ。
   ブラウザ自動操作で eBay を触るコードを追加しない。
2. **Sold データは Browse API では取れない**（Active のみ）。落札相場は Seller Hub > Product Research の
   CSV を `data/research_csv/` に置いて読む。外部 Sold API を足す場合は `01_analyze_market.py` の
   `SoldDataSource` プロトコルを実装して差し替える。
3. **`publishOffer` は DB 上 `APPROVED` のレコードのみ**。`lib/ebay_client.assert_publishable()` が
   クライアント層で強制し、`03_publish_ebay.py` は公開直前に DB を読み直して再確認する。
   このチェックを迂回・削除する変更は禁止。
4. **認証情報は `.env` のみ**（`python-dotenv`）。ハードコード禁止。`.env` / `*.db` はコミットしない。
5. 開発・テストは **`EBAY_ENV=sandbox`**。API を叩かない検証は **`EBAY_MOCK=1`**。
6. Inventory API で作った未公開 Offer は Seller Hub の Drafts に出ない → 下書き管理は SQLite + `app_review.py`。

## ステータス遷移
```
PENDING ──(UIで承認: 傷/付属品/真贋の3チェック + 利益基準)──▶ APPROVED ──(03)──▶ PUBLISHED ──(04)──▶ OUT_OF_STOCK
   │  ▲                                                          │
   ▼  └──────────── PENDINGに戻す ──────────────────────────────┘
REJECTED
```
`02_create_draft.py` の再実行は PENDING / REJECTED のみ上書きし、APPROVED 以降は触らない。

## 構成
- `scripts/lib/config.py` 設定（config.yaml + .env）
- `scripts/lib/profit.py` 純利益 = 売価USD × (1 − r_fee) × E_rate − C_buy − C_ship、仕入れ上限、容積重量送料
- `scripts/lib/db.py` SQLite（drafts / events）
- `scripts/lib/ebay_client.py` `EbayClient`（実API）/ `MockEbayClient`（同一インターフェース）
- `scripts/lib/listing_gen.py` ルールベース和英変換（glossary）でタイトル≤80字・説明・Item Specifics
- `scripts/lib/source_checker.py` 仕入れ先の在庫・価格判定（JSON-LD → meta → キーワード）
- `scripts/ebay_auth.py` OAuth（Client Credentials / Refresh Token）+ トークンキャッシュ

## 使用 API エンドポイント
- `GET  /buy/browse/v1/item_summary/search` filter=`price:[300..],priceCurrency:USD,itemLocationCountry:JP`
- `PUT  /sell/inventory/v1/inventory_item/{sku}`（Content-Language: en-US 必須）
- `GET  /sell/inventory/v1/offer?sku=` / `POST /sell/inventory/v1/offer` / `PUT /sell/inventory/v1/offer/{id}`
- `POST /sell/inventory/v1/offer/{offerId}/publish`
- `POST /sell/inventory/v1/bulk_update_price_quantity`（1リクエスト最大25件）

## 開発時
- テスト: `python -m pytest -q tests`
- 数値（手数料率・為替・利益基準・送料表）は `config.yaml` で変更し、コードに直書きしない。
