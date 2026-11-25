"""設定読み込み（config.yaml + .env）。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RESEARCH_CSV_DIR = DATA_DIR / "research_csv"
CANDIDATES_DIR = DATA_DIR / "candidates"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = ROOT / "logs"

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    if isinstance(val, str):
        val = val.strip()
    return val or default


def ebay_env() -> str:
    e = (env("EBAY_ENV", "sandbox") or "sandbox").lower()
    if e not in ("sandbox", "production"):
        raise ValueError(f"EBAY_ENV must be sandbox or production, got {e!r}")
    return e


def is_mock() -> bool:
    return (env("EBAY_MOCK", "0") or "0") in ("1", "true", "yes")


def db_path() -> Path:
    return Path(env("DRAFTS_DB_PATH") or DATA_DIR / "drafts.db")
