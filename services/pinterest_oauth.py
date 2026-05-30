import base64
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from urllib.parse import urlencode

import requests
from flask import session

from config import Config
from models import db, OAuthToken

PINTEREST_AUTH_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PROVIDER = "pinterest"
TOKEN_REFRESH_SAFETY_WINDOW = timedelta(minutes=10)


def build_pinterest_authorization_url() -> str:
    """Create the Pinterest authorization URL and store CSRF state in session."""
    if not Config.PINTEREST_CLIENT_ID or not Config.PINTEREST_CLIENT_SECRET:
        raise RuntimeError("Missing PINTEREST_CLIENT_ID or PINTEREST_CLIENT_SECRET in .env")

    state = secrets.token_urlsafe(32)
    session["pinterest_oauth_state"] = state

    params = {
        "client_id": Config.PINTEREST_CLIENT_ID,
        "redirect_uri": Config.PINTEREST_REDIRECT_URI,
        "response_type": "code",
        "scope": Config.PINTEREST_SCOPES,
        "state": state,
    }
    return f"{PINTEREST_AUTH_URL}?{urlencode(params)}"


def validate_pinterest_state(received_state: Optional[str]) -> None:
    expected_state = session.pop("pinterest_oauth_state", None)
    if not expected_state or not received_state or received_state != expected_state:
        raise RuntimeError("Invalid Pinterest OAuth state. Please try connecting again.")


def exchange_code_for_tokens(code: str) -> OAuthToken:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": Config.PINTEREST_REDIRECT_URI,
    }

    # Pinterest docs show continuous_refresh=true for older apps. Newer apps use
    # continuous refresh tokens automatically, but keeping this configurable helps
    # approved apps created before the cutoff.
    if Config.PINTEREST_CONTINUOUS_REFRESH:
        payload["continuous_refresh"] = "true"

    data = _post_token_request(payload)
    return save_pinterest_token_response(data)


def get_valid_pinterest_access_token() -> str:
    """Return a current Pinterest access token, refreshing it when needed."""
    token = OAuthToken.query.filter_by(provider=PROVIDER).first()

    # Backward compatibility for local testing with a manual token.
    # Production should use the OAuth DB token path.
    if not token and Config.PINTEREST_ACCESS_TOKEN:
        return Config.PINTEREST_ACCESS_TOKEN

    if not token:
        raise RuntimeError("Pinterest is not connected. Open /oauth/pinterest/connect first.")

    now = datetime.now(timezone.utc)
    expires_at = _ensure_aware(token.expires_at_utc)

    if expires_at and expires_at <= now + TOKEN_REFRESH_SAFETY_WINDOW:
        token = refresh_pinterest_token(token)

    return token.access_token


def refresh_pinterest_token(token: Optional[OAuthToken] = None) -> OAuthToken:
    token = token or OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token or not token.refresh_token:
        raise RuntimeError("Pinterest refresh token is missing. Reconnect Pinterest.")

    refresh_expires_at = _ensure_aware(token.refresh_token_expires_at_utc)
    if refresh_expires_at and refresh_expires_at <= datetime.now(timezone.utc):
        raise RuntimeError("Pinterest refresh token expired. Reconnect Pinterest.")

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
    }

    # Scope is optional for refresh. Keeping it omitted preserves the granted set.
    data = _post_token_request(payload)
    return save_pinterest_token_response(data, existing_token=token)


def get_pinterest_token_status() -> Dict[str, Any]:
    token = OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token:
        return {"connected": False}

    now = datetime.now(timezone.utc)
    expires_at = _ensure_aware(token.expires_at_utc)
    refresh_expires_at = _ensure_aware(token.refresh_token_expires_at_utc)

    return {
        "connected": True,
        "scope": token.scope,
        "token_type": token.token_type,
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "refresh_token_expires_at_utc": refresh_expires_at.isoformat() if refresh_expires_at else None,
        "access_token_expired": bool(expires_at and expires_at <= now),
        "refresh_token_expired": bool(refresh_expires_at and refresh_expires_at <= now),
        "updated_at_utc": _ensure_aware(token.updated_at).isoformat() if token.updated_at else None,
    }


def save_pinterest_token_response(
    data: Dict[str, Any],
    existing_token: Optional[OAuthToken] = None,
) -> OAuthToken:
    now = datetime.now(timezone.utc)

    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError(f"Pinterest token response did not include access_token: {data}")

    expires_at = _seconds_from_now(now, data.get("expires_in"))
    refresh_token_expires_at = _refresh_expiry_from_response(now, data)

    token = existing_token or OAuthToken.query.filter_by(provider=PROVIDER).first()
    if not token:
        token = OAuthToken(provider=PROVIDER)
        db.session.add(token)

    token.access_token = access_token
    token.refresh_token = data.get("refresh_token") or token.refresh_token
    token.token_type = data.get("token_type") or token.token_type
    token.scope = data.get("scope") or token.scope
    token.expires_at_utc = expires_at or token.expires_at_utc
    token.refresh_token_expires_at_utc = refresh_token_expires_at or token.refresh_token_expires_at_utc
    token.raw_response_json = json.dumps(data, ensure_ascii=False)

    db.session.commit()
    return token


def _post_token_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    auth_header = _basic_auth_header(Config.PINTEREST_CLIENT_ID, Config.PINTEREST_CLIENT_SECRET)
    response = requests.post(
        PINTEREST_TOKEN_URL,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=payload,
        timeout=60,
    )

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1000]}

    if not response.ok:
        raise RuntimeError(f"Pinterest token request failed: HTTP {response.status_code}: {data}")

    return data


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"Basic {encoded}"


def _seconds_from_now(now: datetime, seconds: Any) -> Optional[datetime]:
    try:
        return now + timedelta(seconds=int(seconds))
    except Exception:
        return None


def _refresh_expiry_from_response(now: datetime, data: Dict[str, Any]) -> Optional[datetime]:
    # Pinterest may return an absolute unix timestamp on refresh responses.
    if data.get("refresh_token_expires_at"):
        try:
            return datetime.fromtimestamp(int(data["refresh_token_expires_at"]), tz=timezone.utc)
        except Exception:
            pass

    # Authorization-code responses can return a relative lifetime.
    if data.get("refresh_token_expires_in"):
        return _seconds_from_now(now, data.get("refresh_token_expires_in"))

    return None


def _ensure_aware(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

# ---- Pinterest board discovery/cache ----
from services.destination_cache import cache_is_fresh, get_cached_options, upsert_cached_options  # noqa: E402

OPTION_TYPE_BOARDS = "boards"
PINTEREST_API_BASE = "https://api.pinterest.com/v5"


def list_pinterest_boards(force: bool = False) -> list[dict]:
    """Return boards from local cache, refreshing from Pinterest when needed."""
    if not force and cache_is_fresh(PROVIDER, OPTION_TYPE_BOARDS):
        return get_cached_options(PROVIDER, OPTION_TYPE_BOARDS)

    access_token = get_valid_pinterest_access_token()
    boards = []
    bookmark = None

    while True:
        params = {"page_size": 100}
        if bookmark:
            params["bookmark"] = bookmark

        response = requests.get(
            f"{PINTEREST_API_BASE}/boards",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=60,
        )

        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text[:1000]}

        if not response.ok:
            raise RuntimeError(f"Pinterest boards request failed: HTTP {response.status_code}: {data}")

        for item in data.get("items", []):
            board_id = item.get("id")
            if not board_id:
                continue
            boards.append({
                "id": board_id,
                "name": item.get("name") or board_id,
                "extra": {
                    "privacy": item.get("privacy"),
                    "description": item.get("description"),
                    "owner": item.get("owner"),
                    "pin_count": item.get("pin_count"),
                    "follower_count": item.get("follower_count"),
                },
            })

        bookmark = data.get("bookmark")
        if not bookmark:
            break

    return upsert_cached_options(PROVIDER, OPTION_TYPE_BOARDS, boards)
