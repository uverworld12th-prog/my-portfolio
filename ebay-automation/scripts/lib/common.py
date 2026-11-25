"""スクリプト共通ユーティリティ。"""
from __future__ import annotations

import hashlib
import logging
import re
import sys

from .config import LOG_DIR, ebay_env, is_mock

MODEL_TOKEN_RE = re.compile(r"\b(?=[A-Za-z0-9\-/\.]*\d)(?=[A-Za-z0-9\-/\.]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9\-/\.]{1,}\b")


def setup_logging(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")):
            h.setFormatter(fmt)
            logger.addHandler(h)
    return logger


def banner(logger: logging.Logger) -> None:
    logger.info("EBAY_ENV=%s%s", ebay_env(), " (MOCK: eBay APIは呼び出しません)" if is_mock() else "")
    if ebay_env() == "production" and not is_mock():
        logger.warning("⚠ PRODUCTION 環境で実行しています")


GENERATION_RE = r"(?:\s+(?:Mark\s*|MK\s*)?(?:II|III|IV|V|VI|[2-6])\b)?"
_UNIT_RE = re.compile(r"\d+(\.\d+)?(mm|g|kg|cm)?|f/?\d+(\.\d+)?|\d+-\d+mm", re.I)


def extract_model(title: str) -> str | None:
    """タイトルから型番らしきトークン（英字+数字混在）を抽出。

    "Z6 II" / "EOS 5D Mark IV" のような世代表記は型番に含める（Z6 と Z6 II を混同しない）。
    """
    for m in MODEL_TOKEN_RE.finditer(title or ""):
        if _UNIT_RE.fullmatch(m.group(0)):
            continue
        gen = re.match(GENERATION_RE, title[m.end():], re.I)
        tail = gen.group(0) if gen and gen.group(0).strip() else ""
        # "Z6 2" のような数字のみの後続は型番の一部と断定できないので II 系のみ採用
        if tail and re.fullmatch(r"\s+[2-6]", tail):
            tail = ""
        return re.sub(r"\s+", " ", (m.group(0) + tail).upper())
    return None


def normalize_key(s: str | None) -> str:
    """照合用キー（英数字のみ・大文字）。"Z6 II" → "Z6II" """
    return re.sub(r"[^A-Za-z0-9]", "", s or "").upper()


def make_sku(brand: str, model: str, source_url: str) -> str:
    """英数字とハイフンのみ・50文字以内の決定的SKU。"""
    prefix = re.sub(r"[^A-Za-z0-9]", "", f"{brand[:4]}{model}")[:20].upper() or "ITEM"
    h = hashlib.sha1(source_url.encode()).hexdigest()[:8].upper()
    return f"JP-{prefix}-{h}"
