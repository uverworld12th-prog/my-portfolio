"""ローカル下書き確認・承認UI（Streamlit）。

起動: streamlit run app_review.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from lib import db  # noqa: E402
from lib.config import ebay_env, is_mock, load_config  # noqa: E402
from lib.profit import calc_profit  # noqa: E402

st.set_page_config(page_title="eBay 下書き・承認ボックス", page_icon="📦", layout="wide")
cfg = load_config()
TITLE_MAX = cfg["listing"]["title_max_len"]
CHECKS = ["傷・状態を写真と仕入れ元ページで確認した", "付属品（箱・キャップ・充電器等）を確認した",
          "真贋・型番の一致を確認した"]
COLOR = {"PENDING": "🟡", "APPROVED": "🟢", "REJECTED": "⚫", "PUBLISHED": "🔵", "OUT_OF_STOCK": "🔴", "ERROR": "🟠"}

st.title("📦 eBay 下書き・承認ボックス")
env_label = f"環境: **{ebay_env()}**" + ("（MOCK）" if is_mock() else "")
(st.error if ebay_env() == "production" and not is_mock() else st.caption)(env_label)

with db.connect() as conn:
    all_rows = db.fetch(conn)

counts = pd.Series([r["status"] for r in all_rows]).value_counts().to_dict() if all_rows else {}
cols = st.columns(len(db.STATUSES))
for c, s in zip(cols, db.STATUSES):
    c.metric(f"{COLOR[s]} {s}", counts.get(s, 0))

tab_review, tab_all, tab_log = st.tabs(["✅ 承認待ち", "📋 全件一覧", "🧾 イベントログ"])

with tab_review:
    status_filter = st.radio("表示するステータス", ["PENDING", "APPROVED", "REJECTED", "ERROR"], horizontal=True)
    rows = [r for r in all_rows if r["status"] == status_filter]
    if not rows:
        st.info(f"{status_filter} のレコードはありません。")
    for r in rows:
        sku = r["sku"]
        head = (f"{COLOR[r['status']]} {sku} ｜ ${r['sell_price_usd']:.2f} ｜ "
                f"利益 {r['expected_profit_jpy']:,}円 ({r['expected_profit_rate']:.1%}) ｜ {r['source_name_ja']}")
        with st.expander(head, expanded=len(rows) <= 3):
            left, right = st.columns([3, 2])
            with right:
                st.markdown("**仕入れ元**")
                st.markdown(f"[{r['source_name_ja']}]({r['source_url']})")
                st.write(f"仕入れ値: **{r['source_price_jpy']:,}円** ／ 送料見込: {r['ship_cost_jpy']:,}円")
                st.write(f"状態メモ: {r['condition_note_ja'] or '—'}")
                if r.get("review_note"):
                    st.warning(r["review_note"])
                if r.get("error_message"):
                    st.error(r["error_message"])
                imgs = r["image_urls"]
                if imgs:
                    st.image(imgs[:4], width=140)
                else:
                    st.warning("画像URLがありません（出品には最低1枚必要）")
            with left:
                title = st.text_input(f"英語タイトル（{TITLE_MAX}文字以内）", r["title_en"], key=f"t_{sku}",
                                      max_chars=TITLE_MAX)
                st.caption(f"{len(title)}/{TITLE_MAX} 文字")
                c1, c2, c3 = st.columns(3)
                price = c1.number_input("売価 (USD)", value=float(r["sell_price_usd"]), step=1.0, key=f"p_{sku}")
                buy = c2.number_input("仕入れ値 (円)", value=int(r["source_price_jpy"]), step=500, key=f"b_{sku}")
                cond = c3.selectbox("コンディション", ["NEW", "NEW_OTHER", "LIKE_NEW", "USED_EXCELLENT",
                                    "USED_VERY_GOOD", "USED_GOOD", "USED_ACCEPTABLE", "FOR_PARTS_OR_NOT_WORKING"],
                                    index=None, placeholder=r["condition"], key=f"c_{sku}") or r["condition"]
                pr = calc_profit(cfg, price, buy, r["ship_cost_jpy"])
                (st.success if pr.passes else st.error)(
                    f"純利益 {pr.profit_jpy:,}円 ／ 利益率 {pr.profit_rate:.1%} ／ 受取 {pr.revenue_jpy:,}円"
                    + ("" if pr.passes else " — 利益基準未達"))
                desc = st.text_area("説明文 (HTML)", r["description_en"], height=180, key=f"d_{sku}")
                spec_txt = st.text_area("Item Specifics (JSON)",
                                        json.dumps(r["item_specifics"], ensure_ascii=False, indent=1),
                                        height=140, key=f"s_{sku}")
                img_txt = st.text_area("画像URL（1行1つ）", "\n".join(imgs), height=80, key=f"i_{sku}")

            checks = [st.checkbox(c, key=f"chk{i}_{sku}") for i, c in enumerate(CHECKS)] \
                if r["status"] == "PENDING" else []
            b1, b2, b3, _ = st.columns([1, 1, 1, 3])

            def _save(new_status: str | None = None):
                try:
                    spec = json.loads(spec_txt)
                    assert isinstance(spec, dict)
                    spec = {k: v if isinstance(v, list) else [str(v)] for k, v in spec.items()}
                except (ValueError, AssertionError):
                    st.error("Item Specifics の JSON が不正です")
                    return
                with db.connect() as c:
                    db.update_fields(c, sku, title_en=title, sell_price_usd=price, source_price_jpy=int(buy),
                                     condition=cond, description_en=desc, item_specifics=spec,
                                     image_urls=[u.strip() for u in img_txt.splitlines() if u.strip()],
                                     expected_profit_jpy=pr.profit_jpy, expected_profit_rate=pr.profit_rate,
                                     error_message=None)
                    if new_status:
                        db.set_status(c, sku, new_status, "via app_review")
                    else:
                        db.log_event(c, sku, "EDITED", "via app_review")
                st.rerun()

            if b1.button("💾 保存", key=f"save_{sku}"):
                _save()
            if r["status"] == "PENDING":
                ready = all(checks) and pr.passes and len(title) <= TITLE_MAX
                if b2.button("✅ 承認", key=f"ok_{sku}", disabled=not ready, type="primary",
                             help=None if ready else "3項目のチェックと利益基準クリアが必要です"):
                    _save("APPROVED")
                if b3.button("⛔ 却下", key=f"ng_{sku}"):
                    _save("REJECTED")
            elif r["status"] in ("APPROVED", "REJECTED", "ERROR"):
                if b2.button("↩ PENDINGに戻す", key=f"back_{sku}"):
                    _save("PENDING")

with tab_all:
    if all_rows:
        df = pd.DataFrame(all_rows)[["sku", "status", "title_en", "sell_price_usd", "source_price_jpy",
                                     "expected_profit_jpy", "expected_profit_rate", "listing_id",
                                     "last_checked_at", "source_url"]]
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"source_url": st.column_config.LinkColumn("仕入れ元")})
    else:
        st.info("データがありません。`python scripts/02_create_draft.py` を実行してください。")

with tab_log:
    with db.connect() as conn:
        ev = pd.read_sql_query("SELECT created_at, sku, event, detail FROM events ORDER BY id DESC LIMIT 300", conn)
    st.dataframe(ev, use_container_width=True, hide_index=True)
