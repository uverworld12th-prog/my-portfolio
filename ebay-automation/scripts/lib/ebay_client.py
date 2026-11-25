"""eBay 公式 API クライアント（Browse API / Inventory API）。

スクレイピングは一切行わない。EBAY_MOCK=1 のときは MockEbayClient を返し、
ネットワークを使わずに全工程を検証できる。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import requests

from .config import env, is_mock


class EbayApiError(RuntimeError):
    def __init__(self, status: int, body: Any, msg: str = ""):
        self.status, self.body = status, body
        super().__init__(f"{msg} HTTP {status}: {str(body)[:500]}")

    def error_ids(self) -> list[int]:
        try:
            return [e.get("errorId") for e in self.body.get("errors", [])]
        except AttributeError:
            return []


class PublishNotAllowed(RuntimeError):
    """APPROVED 以外のレコードを公開しようとした。"""


def assert_publishable(record: dict) -> None:
    """安全制約: DB上 APPROVED のレコードのみ publishOffer を許可。"""
    if not record or record.get("status") != "APPROVED":
        raise PublishNotAllowed(
            f"SKU {record.get('sku') if record else '?'} は status={record.get('status') if record else None} のため公開できません（APPROVEDのみ可）")


def build_search_filter(min_price_usd: float, country: str, currency: str = "USD") -> str:
    return f"price:[{min_price_usd}..],priceCurrency:{currency},itemLocationCountry:{country}"


class EbayClient:
    def __init__(self, marketplace_id: str | None = None):
        import ebay_auth  # scripts/ebay_auth.py
        self.auth = ebay_auth
        self.base = ebay_auth.api_base()
        self.marketplace = marketplace_id or env("EBAY_MARKETPLACE_ID", "EBAY_US")

    # ---------- low level ----------
    def _req(self, method: str, path: str, *, user: bool, retries: int = 3, **kw) -> Any:
        token = self.auth.get_user_token() if user else self.auth.get_application_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                   "X-EBAY-C-MARKETPLACE-ID": self.marketplace}
        if "json" in kw:
            headers["Content-Type"] = "application/json"
            headers["Content-Language"] = "en-US"
        headers.update(kw.pop("headers", {}))
        for attempt in range(retries):
            r = requests.request(method, self.base + path, headers=headers, timeout=30, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            break
        body: Any = None
        if r.content:
            try:
                body = r.json()
            except ValueError:
                body = r.text
        if r.status_code >= 400:
            raise EbayApiError(r.status_code, body, f"{method} {path}")
        return body

    # ---------- Browse API (Active listings only) ----------
    def search_items(self, q: str, min_price_usd: float = 300, country: str = "JP",
                     limit: int = 50, sort: str = "price", category_ids: str | None = None) -> dict:
        params = {"q": q, "filter": build_search_filter(min_price_usd, country),
                  "limit": min(limit, 200), "sort": sort}
        if category_ids:
            params["category_ids"] = category_ids
        return self._req("GET", "/buy/browse/v1/item_summary/search", user=False, params=params) or {}

    # ---------- Inventory API ----------
    def put_inventory_item(self, sku: str, payload: dict) -> None:
        self._req("PUT", f"/sell/inventory/v1/inventory_item/{sku}", user=True, json=payload)

    def get_offers(self, sku: str) -> list[dict]:
        try:
            body = self._req("GET", "/sell/inventory/v1/offer", user=True,
                             params={"sku": sku, "marketplace_id": self.marketplace})
        except EbayApiError as e:
            if e.status == 404:
                return []
            raise
        return (body or {}).get("offers", [])

    def create_offer(self, payload: dict) -> str:
        return self._req("POST", "/sell/inventory/v1/offer", user=True, json=payload)["offerId"]

    def update_offer(self, offer_id: str, payload: dict) -> None:
        self._req("PUT", f"/sell/inventory/v1/offer/{offer_id}", user=True, json=payload)

    def publish_offer(self, offer_id: str, record: dict) -> str:
        assert_publishable(record)
        return self._req("POST", f"/sell/inventory/v1/offer/{offer_id}/publish", user=True, json={})["listingId"]

    def bulk_update_price_quantity(self, requests_: list[dict]) -> list[dict]:
        body = self._req("POST", "/sell/inventory/v1/bulk_update_price_quantity", user=True,
                         json={"requests": requests_})
        return (body or {}).get("responses", [])


class MockEbayClient:
    """ネットワーク不要のモック。決定的な疑似データを返す。"""

    def __init__(self, marketplace_id: str | None = None):
        self.marketplace = marketplace_id or "EBAY_US"
        self.calls: list[tuple] = []
        self._offers: dict[str, dict] = {}

    @staticmethod
    def _h(s: str) -> int:
        return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)

    def search_items(self, q: str, min_price_usd: float = 300, country: str = "JP",
                     limit: int = 50, sort: str = "price", category_ids: str | None = None) -> dict:
        self.calls.append(("search_items", q))
        import json
        from .common import normalize_key
        from .config import DATA_DIR
        h = self._h(q)
        total = 3 + h % 25
        f = DATA_DIR / "mock_market.json"
        market = json.loads(f.read_text()) if f.exists() else {}
        base = market.get(normalize_key(q)) or max(min_price_usd, 350 + h % 900)
        items = []
        for i in range(min(total, limit)):
            # 先頭1件は相場の3割程度の「ジャンク/付属品」外れ値を混ぜる
            price = round(base * 0.3 if i == 0 else base * (0.95 + i * 0.04), 2)
            items.append({
                "itemId": f"v1|{100000000000 + (h + i) % 899999999999}|0",
                "title": f"{q} [MOCK #{i + 1}] from Japan",
                "price": {"value": f"{price:.2f}", "currency": "USD"},
                "condition": ["Used", "Pre-owned", "New"][i % 3],
                "itemLocation": {"country": country},
                "itemWebUrl": f"https://www.ebay.com/itm/{100000000000 + (h + i) % 899999999999}",
                "seller": {"username": f"mock_seller_{i}"},
            })
        return {"total": total, "itemSummaries": items}

    def put_inventory_item(self, sku: str, payload: dict) -> None:
        self.calls.append(("put_inventory_item", sku))

    def get_offers(self, sku: str) -> list[dict]:
        return [o for o in self._offers.values() if o["sku"] == sku]

    def create_offer(self, payload: dict) -> str:
        oid = f"MOCKOFFER{self._h(payload['sku']) % 10**8:08d}"
        self._offers[oid] = {**payload, "offerId": oid, "status": "UNPUBLISHED"}
        self.calls.append(("create_offer", payload["sku"]))
        return oid

    def update_offer(self, offer_id: str, payload: dict) -> None:
        self.calls.append(("update_offer", offer_id))

    def publish_offer(self, offer_id: str, record: dict) -> str:
        assert_publishable(record)
        self.calls.append(("publish_offer", offer_id))
        if offer_id in self._offers:
            self._offers[offer_id]["status"] = "PUBLISHED"
        return f"MOCKLISTING{self._h(offer_id) % 10**9:09d}"

    def bulk_update_price_quantity(self, requests_: list[dict]) -> list[dict]:
        self.calls.append(("bulk_update_price_quantity", [r["sku"] for r in requests_]))
        return [{"sku": r["sku"], "statusCode": 200} for r in requests_]


def get_client(marketplace_id: str | None = None):
    return MockEbayClient(marketplace_id) if is_mock() else EbayClient(marketplace_id)
