"""仕入れ先の在庫・価格チェック。

汎用実装: ページHTMLから
  1) JSON-LD (schema.org Product/Offer) の availability / price
  2) <meta property="product:price:amount"> 等
  3) 売切れキーワード（config.yaml monitor.soldout_keywords）
を順に見る。サイトごとの精度が必要なら SITE_CHECKERS にドメイン別関数を追加する。

※ 仕入れ先サイトの利用規約・robots.txt を必ず確認し、公式APIがあればそちらを使うこと。
  アクセス間隔は monitor.request_interval_sec で調整する。

EBAY_MOCK=1 のときは data/mock_source_status.json を参照（ネットワーク不使用）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import requests

from .config import DATA_DIR, is_mock

UA = "Mozilla/5.0 (compatible; stock-monitor/1.0; personal use)"


@dataclass
class SourceStatus:
    in_stock: bool | None      # None = 判定不能
    price_jpy: int | None
    reason: str = ""


def _jsonld_offers(html: str):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "offers" in d:
                    offers = d["offers"]
                    yield from (offers if isinstance(offers, list) else [offers])
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)


def parse_html(html: str, soldout_keywords: list[str]) -> SourceStatus:
    for off in _jsonld_offers(html):
        if not isinstance(off, dict):
            continue
        avail = str(off.get("availability", ""))
        price = off.get("price") or (off.get("priceSpecification") or {}).get("price")
        p = int(float(price)) if price not in (None, "") else None
        if avail:
            return SourceStatus("InStock" in avail or "LimitedAvailability" in avail, p, f"json-ld {avail.rsplit('/', 1)[-1]}")
        if p:
            return SourceStatus(None, p, "json-ld price only")
    price = None
    m = re.search(r'<meta[^>]+(?:product:price:amount|og:price:amount)[^>]+content="([\d.,]+)"', html, re.I)
    if m:
        price = int(float(m.group(1).replace(",", "")))
    text = re.sub(r"<[^>]+>", " ", html)
    for kw in soldout_keywords:
        if kw in text:
            return SourceStatus(False, price, f"keyword '{kw}'")
    return SourceStatus(True if price else None, price, "meta price" if price else "判定材料なし")


SITE_CHECKERS: dict[str, Callable[[str, dict], SourceStatus]] = {}


def check(url: str, cfg: dict) -> SourceStatus:
    mon = cfg["monitor"]
    if is_mock():
        fixtures = json.loads((DATA_DIR / "mock_source_status.json").read_text(encoding="utf-8")) \
            if (DATA_DIR / "mock_source_status.json").exists() else {}
        f = fixtures.get(url)
        if f is None:
            return SourceStatus(True, None, "mock: 既定=在庫あり")
        return SourceStatus(f.get("in_stock"), f.get("price_jpy"), "mock fixture")
    host = urlparse(url).netloc
    if host in SITE_CHECKERS:
        return SITE_CHECKERS[host](url, cfg)
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=mon["request_timeout_sec"])
    except requests.RequestException as e:
        return SourceStatus(None, None, f"取得失敗: {e}")
    if r.status_code == 404:
        return SourceStatus(False, None, "404 (削除済み)")
    if r.status_code >= 400:
        return SourceStatus(None, None, f"HTTP {r.status_code}")
    return parse_html(r.text, mon["soldout_keywords"])
