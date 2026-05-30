import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from flask import session

from config import Config
from models import db, OAuthToken
from services.destination_cache import (
    cache_is_fresh,
    get_cached_option,
    get_cached_options,
    upsert_cached_options,
)

PROVIDER = "facebook"
OPTION_TYPE_PAGES = "pages"
FACEBOOK_AUTH_URL = "https://www.facebook.com/dialog/oauth"
GRAPH_BASE = "https://graph.facebook.com"
TOKEN_REFRESH_SAFETY_WINDOW = timedelta(days=3)


def build_facebook_authorization_url() -> str:
    if not Config.FACEBOOK_APP_ID or not Config.FACEBOOK_APP_SECRET:
        raise RuntimeError("Missing FACEBOOK_APP_ID or FACEBOOK_APP_SECRET in .env")

    state = secrets.token_urlsafe(32)
    session["facebook_oauth_state"] = state

    params = {
        "client_id": Config.FACEBOOK_APP_ID,
        "redirect_uri": Config.FACEBOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": Config.FACEBOOK_SCOPES,
        "state": state,
    }
    return f"{FACEBOOK_AUTH_URL}?{urlencode(params)}"


def validate_facebook_state(received_state: Optional[str]) -> None:
    expected_state = session.pop("facebook_oauth_state", None)
    if not expected_state or not received_state or received_state != expected_state:
        raise RuntimeError("Invalid Facebook OAuth state. Please try connecting again.")


def exchange_facebook_code_for_token(code: str) -> OAuthToken:
    short_lived = _get(
        f"{GRAPH_BASE}/{Config.FACEBOOK_GRAPH_VERSION}/oauth/access_token",
        params={
            "client_id": Config.FACEBOOK_APP_ID,
            "client_secret": Config.FACEBOOK_APP_SECRET,
            "redirect_uri": Config.FACEBOOK_REDIRECT_URI,
            "code": code,
        },
    )

    access_token = short_lived.get("access_token")
    if not access_token:
        raise RuntimeError(f"Facebook token response missing access_token: {short_lived}")

    # Exchange for a long-lived user token. For local/personal use, this avoids
    # reconnecting every few hours. Meta commonly returns expires_in here.
    long_lived = _get(
        f"{GRAPH_BASE}/{Config.FACEBOOK_GRAPH_VERSION}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": Config.FACEBOOK_APP_ID,
            "client_secret": Config.FACEBOOK_APP_SECRET,
            "fb_exchange_token": access_token,
        },
    )

    return save_facebook_token_response(long_lived or short_lived)


def save_facebook_token_response(data: Dict[str, Any]) -> OAuthToken:
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError(f"Facebook token response missing access_token: {data}")

    now = datetime.now(timezone.utc)
    token = OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token:
        token = OAuthToken(provider=PROVIDER)
        db.session.add(token)

    token.access_token = access_token
    token.refresh_token = None
    token.token_type = data.get("token_type") or token.token_type or "bearer"
    token.scope = data.get("scope") or Config.FACEBOOK_SCOPES
    token.expires_at_utc = _seconds_from_now(now, data.get("expires_in")) or token.expires_at_utc
    token.refresh_token_expires_at_utc = None
    token.raw_response_json = json.dumps(data, ensure_ascii=False)
    db.session.commit()
    return token


def get_facebook_token_status() -> Dict[str, Any]:
    token = OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token:
        return {"connected": False}

    now = datetime.now(timezone.utc)
    expires_at = _ensure_aware(token.expires_at_utc)
    return {
        "connected": True,
        "scope": token.scope,
        "token_type": token.token_type,
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "access_token_expired": bool(expires_at and expires_at <= now),
        "updated_at_utc": _ensure_aware(token.updated_at).isoformat() if token.updated_at else None,
    }


def get_valid_facebook_user_access_token() -> str:
    token = OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token:
        raise RuntimeError("Facebook is not connected. Open /oauth/facebook/connect first.")

    expires_at = _ensure_aware(token.expires_at_utc)
    if expires_at and expires_at <= datetime.now(timezone.utc):
        raise RuntimeError("Facebook user token expired. Reconnect Facebook.")

    if expires_at and expires_at <= datetime.now(timezone.utc) + TOKEN_REFRESH_SAFETY_WINDOW:
        # Facebook does not use OAuth refresh tokens in this flow. Re-exchanging a
        # still-valid long-lived token can extend it for many app configurations.
        try:
            extended = _get(
                f"{GRAPH_BASE}/{Config.FACEBOOK_GRAPH_VERSION}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": Config.FACEBOOK_APP_ID,
                    "client_secret": Config.FACEBOOK_APP_SECRET,
                    "fb_exchange_token": token.access_token,
                },
            )
            token = save_facebook_token_response(extended)
        except Exception:
            # Keep current token if it is still valid. The next reconnect warning
            # is better than breaking uploads prematurely.
            pass

    return token.access_token


def list_facebook_pages(force: bool = False) -> List[Dict[str, Any]]:
    if not force and cache_is_fresh(PROVIDER, OPTION_TYPE_PAGES):
        return get_cached_options(PROVIDER, OPTION_TYPE_PAGES)

    token = get_valid_facebook_user_access_token()
    pages: List[Dict[str, Any]] = []
    url = f"{GRAPH_BASE}/{Config.FACEBOOK_GRAPH_VERSION}/me/accounts"
    params = {
        "access_token": token,
        "fields": "id,name,access_token,category,tasks",
        "limit": 100,
    }

    while url:
        data = _get(url, params=params)
        params = None
        for item in data.get("data", []):
            page_id = item.get("id")
            name = item.get("name") or page_id
            if not page_id:
                continue
            pages.append({
                "id": page_id,
                "name": name,
                "extra": {
                    "page_access_token": item.get("access_token"),
                    "category": item.get("category"),
                    "tasks": item.get("tasks") or [],
                },
            })
        url = (data.get("paging") or {}).get("next")

    return upsert_cached_options(PROVIDER, OPTION_TYPE_PAGES, pages)


def get_facebook_page_destination(page_id: Optional[str]) -> Dict[str, Any]:
    # Dynamic selected Page path.
    if page_id:
        cached = get_cached_option(PROVIDER, OPTION_TYPE_PAGES, page_id)
        if cached:
            token = (cached.get("extra") or {}).get("page_access_token")
            if token:
                return {
                    "page_id": cached["id"],
                    "page_name": cached["name"],
                    "page_access_token": token,
                }

        # Cache may be stale/missing. Try a forced refresh once.
        list_facebook_pages(force=True)
        cached = get_cached_option(PROVIDER, OPTION_TYPE_PAGES, page_id)
        if cached:
            token = (cached.get("extra") or {}).get("page_access_token")
            if token:
                return {
                    "page_id": cached["id"],
                    "page_name": cached["name"],
                    "page_access_token": token,
                }

        raise RuntimeError(f"Facebook Page {page_id} not found in cache or missing Page access token.")

    # Backward-compatible single Page fallback.
    if Config.FACEBOOK_PAGE_ID and Config.FACEBOOK_PAGE_ACCESS_TOKEN:
        return {
            "page_id": Config.FACEBOOK_PAGE_ID,
            "page_name": "Configured Facebook Page",
            "page_access_token": Config.FACEBOOK_PAGE_ACCESS_TOKEN,
        }

    raise RuntimeError("Choose a Facebook Page or set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN in .env")


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.get(url, params=params, timeout=60)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1000]}
    if not response.ok:
        raise RuntimeError(f"Facebook API request failed: HTTP {response.status_code}: {data}")
    return data


def _seconds_from_now(now: datetime, seconds: Any) -> Optional[datetime]:
    try:
        return now + timedelta(seconds=int(seconds))
    except Exception:
        return None


def _ensure_aware(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
