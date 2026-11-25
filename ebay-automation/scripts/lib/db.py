"""SQLite（下書き・承認ボックス）。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import db_path

STATUSES = ("PENDING", "APPROVED", "REJECTED", "PUBLISHED", "OUT_OF_STOCK", "ERROR")

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT UNIQUE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    source_name_ja  TEXT,
    source_url      TEXT,
    source_price_jpy INTEGER,
    condition_note_ja TEXT,
    title_en        TEXT,
    description_en  TEXT,
    item_specifics  TEXT,          -- JSON
    image_urls      TEXT,          -- JSON
    condition       TEXT,          -- eBay ConditionEnum
    category_id     TEXT,
    sell_price_usd  REAL,
    ship_cost_jpy   INTEGER,
    expected_profit_jpy INTEGER,
    expected_profit_rate REAL,
    offer_id        TEXT,
    listing_id      TEXT,
    last_checked_at TEXT,
    last_source_price_jpy INTEGER,
    review_note     TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sku        TEXT,
    event      TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(path: Path | str | None = None):
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_event(conn, sku: str | None, event: str, detail: dict | str | None = None) -> None:
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False)
    conn.execute("INSERT INTO events (sku, event, detail, created_at) VALUES (?,?,?,?)",
                 (sku, event, detail, now()))


def upsert_draft(conn, rec: dict) -> str:
    """PENDING として登録。既存SKUは PENDING/REJECTED の場合のみ上書き。"""
    rec = dict(rec)
    for k in ("item_specifics", "image_urls"):
        if k in rec and not isinstance(rec[k], str):
            rec[k] = json.dumps(rec[k], ensure_ascii=False)
    row = conn.execute("SELECT status FROM drafts WHERE sku=?", (rec["sku"],)).fetchone()
    ts = now()
    if row is None:
        rec.update(status="PENDING", created_at=ts, updated_at=ts)
        cols = ",".join(rec)
        conn.execute(f"INSERT INTO drafts ({cols}) VALUES ({','.join('?' * len(rec))})",
                     tuple(rec.values()))
        log_event(conn, rec["sku"], "DRAFT_CREATED")
        return "created"
    if row["status"] in ("PENDING", "REJECTED"):
        rec.update(status="PENDING", updated_at=ts)
        sets = ",".join(f"{k}=?" for k in rec if k != "sku")
        conn.execute(f"UPDATE drafts SET {sets} WHERE sku=?",
                     tuple(v for k, v in rec.items() if k != "sku") + (rec["sku"],))
        log_event(conn, rec["sku"], "DRAFT_UPDATED")
        return "updated"
    return f"skipped ({row['status']})"


def update_fields(conn, sku: str, **fields) -> None:
    for k in ("item_specifics", "image_urls"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"invalid status {fields['status']}")
    fields["updated_at"] = now()
    sets = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE drafts SET {sets} WHERE sku=?", (*fields.values(), sku))


def set_status(conn, sku: str, status: str, note: str | None = None) -> None:
    update_fields(conn, sku, status=status)
    log_event(conn, sku, f"STATUS_{status}", note)


def fetch(conn, status: str | None = None) -> list[dict]:
    if status:
        rows = conn.execute("SELECT * FROM drafts WHERE status=? ORDER BY id", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM drafts ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("item_specifics", "image_urls"):
            d[k] = json.loads(d[k]) if d.get(k) else ({} if k == "item_specifics" else [])
        out.append(d)
    return out


def get(conn, sku: str) -> dict | None:
    r = conn.execute("SELECT * FROM drafts WHERE sku=?", (sku,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["item_specifics"] = json.loads(d["item_specifics"]) if d.get("item_specifics") else {}
    d["image_urls"] = json.loads(d["image_urls"]) if d.get("image_urls") else []
    return d
