"""eBay OAuth トークン取得・自動リフレッシュ共通モジュール。

- Application Token（Client Credentials Grant）: Browse API 用
- User Access Token（Refresh Token Grant）: Inventory API 用（scope: sell.inventory）

トークンは data/.token_cache.json にキャッシュし、期限60秒前に自動更新する。
認証情報は .env からのみ読み込む（ハードコード禁止）。

単体実行で疎通確認:  python scripts/ebay_auth.py
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import DATA_DIR, ebay_env, env, is_mock  # noqa: E402

TOKEN_URLS = {
    "sandbox": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
    "production": "https://api.ebay.com/identity/v1/oauth2/token",
}
API_BASES = {
    "sandbox": "https://api.sandbox.ebay.com",
    "production": "https://api.ebay.com",
}
APP_SCOPES = ["https://api.ebay.com/oauth/api_scope"]
USER_SCOPES = [
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
]
CACHE_FILE = DATA_DIR / ".token_cache.json"


class EbayAuthError(RuntimeError):
    pass


def api_base() -> str:
    return API_BASES[ebay_env()]


def _basic_auth_header() -> str:
    cid, secret = env("EBAY_CLIENT_ID"), env("EBAY_CLIENT_SECRET")
    if not cid or not secret:
        raise EbayAuthError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET が .env に設定されていません")
    return "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))
    try:
        CACHE_FILE.chmod(0o600)
    except OSError:
        pass


def _request_token(data: dict) -> dict:
    resp = requests.post(
        TOKEN_URLS[ebay_env()],
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Authorization": _basic_auth_header()},
        data=data, timeout=30,
    )
    if resp.status_code != 200:
        raise EbayAuthError(f"トークン取得失敗 HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _get_cached(kind: str, fetcher) -> str:
    key = f"{ebay_env()}:{kind}"
    cache = _load_cache()
    entry = cache.get(key)
    if entry and entry["expires_at"] - 60 > time.time():
        return entry["access_token"]
    tok = fetcher()
    cache[key] = {"access_token": tok["access_token"],
                  "expires_at": time.time() + int(tok.get("expires_in", 7200))}
    _save_cache(cache)
    return tok["access_token"]


def get_application_token() -> str:
    """Browse API 用アプリケーショントークン。"""
    if is_mock():
        return "mock-app-token"
    return _get_cached("app", lambda: _request_token(
        {"grant_type": "client_credentials", "scope": " ".join(APP_SCOPES)}))


def get_user_token() -> str:
    """Inventory API 用ユーザートークン（Refresh Token から自動更新）。"""
    if is_mock():
        return "mock-user-token"
    refresh = env("EBAY_REFRESH_TOKEN")
    if not refresh:
        raise EbayAuthError("EBAY_REFRESH_TOKEN が .env に設定されていません（scope: sell.inventory）")
    return _get_cached("user", lambda: _request_token(
        {"grant_type": "refresh_token", "refresh_token": refresh, "scope": " ".join(USER_SCOPES)}))


def consent_url() -> str:
    """初回の Refresh Token 取得用：ブラウザで開くユーザー同意URL。"""
    from urllib.parse import urlencode
    host = "auth.sandbox.ebay.com" if ebay_env() == "sandbox" else "auth.ebay.com"
    q = urlencode({"client_id": env("EBAY_CLIENT_ID") or "", "response_type": "code",
                   "redirect_uri": env("EBAY_RU_NAME") or "", "scope": " ".join(USER_SCOPES)})
    return f"https://{host}/oauth2/authorize?{q}"


def exchange_code(code: str) -> dict:
    """同意後にリダイレクトされた code を Refresh Token に交換する。"""
    return _request_token({"grant_type": "authorization_code", "code": code,
                           "redirect_uri": env("EBAY_RU_NAME") or ""})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="eBay OAuth 疎通確認")
    ap.add_argument("--consent-url", action="store_true", help="Refresh Token取得用の同意URLを表示")
    ap.add_argument("--exchange-code", help="同意後の code を Refresh Token に交換して表示")
    a = ap.parse_args()
    print(f"EBAY_ENV={ebay_env()} MOCK={is_mock()}")
    if a.consent_url:
        print(consent_url())
    elif a.exchange_code:
        tok = exchange_code(a.exchange_code)
        print("refresh_token を .env の EBAY_REFRESH_TOKEN に設定してください:")
        print(tok.get("refresh_token"))
    else:
        print("Application token:", get_application_token()[:16] + "...")
        try:
            print("User token:       ", get_user_token()[:16] + "...")
        except EbayAuthError as e:
            print("User token:        取得不可 -", e)
