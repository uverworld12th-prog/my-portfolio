"""英語出品データ（タイトル・説明文・Item Specifics）生成。

ルールベース（config.yaml の glossary による和英変換 + テンプレート）。
ここで生成した文面は必ず承認UIで人間が確認・修正する前提。
未翻訳の日本語が残った場合は `untranslated` に列挙して承認者に知らせる。
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

JA_RE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]+")

CONDITION_RULES = [  # (キーワード, eBay ConditionEnum, 表示名) — 上から優先
    ("ジャンク", "FOR_PARTS_OR_NOT_WORKING", "For Parts"),
    ("新品", "NEW", "Brand New"),
    ("未使用", "NEW_OTHER", "Unused"),
    ("極美品", "USED_EXCELLENT", "Near Mint"),
    ("美品", "USED_EXCELLENT", "Excellent"),
    ("良品", "USED_VERY_GOOD", "Very Good"),
]


@dataclass
class GeneratedListing:
    title: str
    description: str
    item_specifics: dict[str, list[str]]
    condition: str
    untranslated: list[str] = field(default_factory=list)


def translate(text: str, glossary: dict[str, str]) -> tuple[str, list[str]]:
    """辞書の長い語から順に置換。残った日本語は未翻訳として返す。"""
    out = text or ""
    for ja in sorted(glossary, key=len, reverse=True):
        out = out.replace(ja, f" {glossary[ja]} ")
    leftovers = JA_RE.findall(out)
    out = JA_RE.sub(" ", out)
    out = re.sub(r"[、。・／/]+", ", ", out)
    out = re.sub(r"\s+", " ", out).strip(" ,")
    out = re.sub(r"\s+,", ",", out)
    return out, leftovers


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _drop_word(text: str, word: str) -> str:
    """note から条件ラベルの重複（"Near Mint. Near Mint ..."）を除く。"""
    out = re.sub(rf"\b{re.escape(word)}\b", "", text or "", count=1, flags=re.I)
    return re.sub(r"\s+", " ", out).strip(" ,")


def detect_condition(note_ja: str) -> tuple[str, str]:
    for kw, enum, label in CONDITION_RULES:
        if kw in (note_ja or ""):
            return enum, label
    return "USED_GOOD", "Good"


def fit_title(parts: list[str], max_len: int = 80) -> str:
    """重要度順の部品を max_len に収まるまで詰める（単語の途中で切らない）。"""
    title = ""
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        cand = f"{title} {p}".strip()
        if len(cand) <= max_len:
            title = cand
        else:
            # 部品単位で入らなければ単語単位で入るだけ入れる
            for w in p.split():
                c2 = f"{title} {w}".strip()
                if len(c2) <= max_len:
                    title = c2
    # 重複語の除去（大文字小文字無視、順序保持）
    seen, words = set(), []
    for w in title.split():
        k = w.lower()
        if k in seen and len(k) > 2:
            continue
        seen.add(k)
        words.append(w)
    return " ".join(words)[:max_len]


def parse_aspects(s: str | None) -> dict[str, list[str]]:
    """"Brand:Nikon;Mount:Nikon F" → {"Brand": ["Nikon"], "Mount": ["Nikon F"]}"""
    out: dict[str, list[str]] = {}
    for chunk in (s or "").split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            if k.strip() and v.strip():
                out[k.strip()] = [x.strip() for x in v.split("|") if x.strip()]
    return out


def generate(cand: dict, cfg: dict) -> GeneratedListing:
    gl = cfg.get("glossary", {})
    max_len = cfg["listing"]["title_max_len"]
    brand = (cand.get("brand") or "").strip()
    model = (cand.get("model") or "").strip()
    item_type = (cand.get("item_type") or "").strip()
    note = cand.get("condition_note_ja") or ""
    cond_enum, cond_label = detect_condition(note + " " + (cand.get("name_ja") or ""))

    name_en, left1 = translate(cand.get("name_ja", ""), gl)
    note_en, left2 = translate(note, gl)
    core_blob = _norm(" ".join([brand, model, item_type, cond_label]))
    extras = [w for w in name_en.replace(",", " ").split() if _norm(w) and _norm(w) not in core_blob]

    suffix = "from JAPAN"
    title = fit_title([
        f"{cond_label}" if cond_enum != "FOR_PARTS_OR_NOT_WORKING" else "",
        brand, model, item_type,
        "For Parts" if cond_enum == "FOR_PARTS_OR_NOT_WORKING" else "",
        " ".join(extras),
    ], max_len - len(suffix) - 1)
    title = f"{title} {suffix}".strip()

    specifics = {"Brand": [brand]} if brand else {}
    if model:
        specifics["Model"] = [model]
    if item_type:
        specifics["Type"] = [item_type]
    specifics["Country/Region of Manufacture"] = ["Japan"]
    specifics.update(parse_aspects(cand.get("aspects")))

    e = html.escape
    desc = (
        f"<h2>{e(title)}</h2>"
        f"<h3>Condition</h3><p>{e(cond_label)}. {e(_drop_word(note_en, cond_label))}</p>"
        "<p>Please check the photos carefully for details. "
        "The item in the photos is the exact item you will receive.</p>"
        f"<h3>Item Specifics</h3><ul>"
        + "".join(f"<li>{e(k)}: {e(', '.join(v))}</li>" for k, v in specifics.items())
        + "</ul>"
        "<h3>Shipping</h3><p>Ships from Japan with tracking via FedEx / DHL. "
        "Carefully packed. Import duties, taxes and charges are not included in the item price "
        "and are the buyer's responsibility.</p>"
        "<h3>Returns</h3><p>Please see the return policy of this listing.</p>"
    )
    return GeneratedListing(title, desc, specifics, cond_enum, sorted(set(left1 + left2)))
