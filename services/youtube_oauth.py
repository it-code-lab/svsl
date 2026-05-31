from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import Config
from services.destination_cache import (
    cache_is_fresh,
    get_cached_option,
    get_cached_options,
    upsert_cached_options,
)

PROVIDER = "youtube"
OPTION_TYPE_CHANNELS = "channels"
OPTION_TYPE_PLAYLISTS_PREFIX = "playlists"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def youtube_token_dir() -> Path:
    token_dir = Path(Config.YOUTUBE_TOKEN_DIR)
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir


def youtube_token_path(channel_id: str) -> Path:
    safe_channel_id = "".join(char for char in channel_id if char.isalnum() or char in ("_", "-"))
    if not safe_channel_id:
        raise RuntimeError("Cannot save YouTube token without a channel ID.")
    return youtube_token_dir() / f"{safe_channel_id}.json"


def get_authenticated_youtube_channels(credentials: Credentials) -> List[Dict[str, Any]]:
    youtube = build("youtube", "v3", credentials=credentials)
    response = (
        youtube.channels()
        .list(part="snippet,contentDetails", mine=True, maxResults=50)
        .execute()
    )

    channels = []
    for item in response.get("items", []):
        channel = _channel_item_to_option(item)
        if channel:
            channels.append(channel)

    if not channels:
        raise RuntimeError(
            "The authorized Google identity did not return a YouTube channel. "
            "Try again and select the channel/Brand Account you want to manage."
        )

    return channels


def save_credentials_for_channels(
    credentials: Credentials,
    channels: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    saved_channels = []

    for channel in channels:
        token_path = youtube_token_path(channel["id"])
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        saved_channels.append(
            {
                "id": channel["id"],
                "name": channel["name"],
                "extra": {
                    **(channel.get("extra") or {}),
                    "token_file": str(token_path),
                },
            }
        )

    upsert_cached_options(PROVIDER, OPTION_TYPE_CHANNELS, saved_channels)
    return saved_channels


def list_youtube_channels(force: bool = False) -> List[Dict[str, Any]]:
    if not force and cache_is_fresh(PROVIDER, OPTION_TYPE_CHANNELS):
        return get_cached_options(PROVIDER, OPTION_TYPE_CHANNELS)

    refreshed = refresh_youtube_channel_cache_from_token_files()
    if refreshed:
        return refreshed

    return get_cached_options(PROVIDER, OPTION_TYPE_CHANNELS)


def refresh_youtube_channel_cache_from_token_files() -> List[Dict[str, Any]]:
    token_files = _youtube_token_files()
    channels = []

    for token_file in token_files:
        try:
            credentials = load_youtube_credentials_from_file(token_file)
            for channel in get_authenticated_youtube_channels(credentials):
                channels.append(
                    {
                        "id": channel["id"],
                        "name": channel["name"],
                        "extra": {
                            **(channel.get("extra") or {}),
                            "token_file": str(token_file),
                        },
                    }
                )
        except Exception:
            # Leave bad/expired files in place; a later upload will return a
            # precise error for that selected channel.
            continue

    if not channels:
        return []

    return upsert_cached_options(PROVIDER, OPTION_TYPE_CHANNELS, channels)


def get_youtube_token_status() -> Dict[str, Any]:
    channels = get_cached_options(PROVIDER, OPTION_TYPE_CHANNELS)
    return {
        "connected": bool(channels or _youtube_token_files()),
        "channel_count": len(channels),
        "token_dir": str(youtube_token_dir()),
        "legacy_token_file": Config.YOUTUBE_TOKEN_FILE,
    }


def list_youtube_playlists(channel_id: str, force: bool = False) -> List[Dict[str, Any]]:
    if not channel_id:
        raise RuntimeError("Choose a YouTube channel before loading playlists.")

    option_type = _playlist_option_type(channel_id)
    if not force and cache_is_fresh(PROVIDER, option_type):
        return get_cached_options(PROVIDER, option_type)

    credentials = get_youtube_credentials_for_channel(channel_id)
    youtube = build("youtube", "v3", credentials=credentials)
    playlists = []
    page_token = None

    while True:
        request = youtube.playlists().list(
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        )
        response = request.execute()

        for item in response.get("items", []):
            playlist = _playlist_item_to_option(item, channel_id)
            if playlist:
                playlists.append(playlist)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return upsert_cached_options(PROVIDER, option_type, playlists)


def get_youtube_credentials_for_channel(channel_id: Optional[str]) -> Credentials:
    token_file = _token_file_for_channel(channel_id)
    return load_youtube_credentials_from_file(token_file)


def load_youtube_credentials_from_file(token_file: Path) -> Credentials:
    if not token_file.exists():
        raise RuntimeError(f"YouTube token file not found: {token_file}")

    credentials = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_file.write_text(credentials.to_json(), encoding="utf-8")

    if not credentials.valid:
        raise RuntimeError(f"YouTube credentials are invalid or expired: {token_file}")

    return credentials


def _token_file_for_channel(channel_id: Optional[str]) -> Path:
    if channel_id:
        cached = get_cached_option(PROVIDER, OPTION_TYPE_CHANNELS, channel_id)
        token_file = ((cached or {}).get("extra") or {}).get("token_file")
        if token_file:
            return Path(token_file)

        candidate = youtube_token_path(channel_id)
        if candidate.exists():
            return candidate

        refresh_youtube_channel_cache_from_token_files()
        cached = get_cached_option(PROVIDER, OPTION_TYPE_CHANNELS, channel_id)
        token_file = ((cached or {}).get("extra") or {}).get("token_file")
        if token_file:
            return Path(token_file)

        raise RuntimeError(
            f"YouTube channel {channel_id} is not connected. "
            "Run scripts/youtube_auth.py and choose that channel."
        )

    channels = get_cached_options(PROVIDER, OPTION_TYPE_CHANNELS)
    if len(channels) == 1:
        token_file = (channels[0].get("extra") or {}).get("token_file")
        if token_file:
            return Path(token_file)

    legacy_token = Path(Config.YOUTUBE_TOKEN_FILE)
    if legacy_token.exists():
        return legacy_token

    if len(channels) > 1:
        raise RuntimeError("Choose a YouTube channel for this job.")

    raise RuntimeError("YouTube is not connected. Run scripts/youtube_auth.py first.")


def _youtube_token_files() -> List[Path]:
    token_files = []

    token_dir = Path(Config.YOUTUBE_TOKEN_DIR)
    if token_dir.exists():
        token_files.extend(sorted(token_dir.glob("*.json")))

    legacy_token = Path(Config.YOUTUBE_TOKEN_FILE)
    if legacy_token.exists() and legacy_token not in token_files:
        token_files.append(legacy_token)

    return token_files


def _playlist_option_type(channel_id: str) -> str:
    return f"{OPTION_TYPE_PLAYLISTS_PREFIX}:{channel_id}"


def _channel_item_to_option(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    channel_id = item.get("id")
    if not channel_id:
        return None

    snippet = item.get("snippet") or {}
    thumbnails = snippet.get("thumbnails") or {}
    default_thumbnail = thumbnails.get("default") or {}
    content_details = item.get("contentDetails") or {}
    related_playlists = content_details.get("relatedPlaylists") or {}

    return {
        "id": channel_id,
        "name": snippet.get("title") or channel_id,
        "extra": {
            "description": snippet.get("description"),
            "custom_url": snippet.get("customUrl"),
            "thumbnail_url": default_thumbnail.get("url"),
            "uploads_playlist_id": related_playlists.get("uploads"),
        },
    }


def _playlist_item_to_option(
    item: Dict[str, Any],
    expected_channel_id: str,
) -> Optional[Dict[str, Any]]:
    playlist_id = item.get("id")
    if not playlist_id:
        return None

    snippet = item.get("snippet") or {}
    channel_id = snippet.get("channelId")
    if channel_id and channel_id != expected_channel_id:
        return None

    content_details = item.get("contentDetails") or {}
    status = item.get("status") or {}

    return {
        "id": playlist_id,
        "name": snippet.get("title") or playlist_id,
        "extra": {
            "channel_id": channel_id or expected_channel_id,
            "description": snippet.get("description"),
            "privacy_status": status.get("privacyStatus"),
            "item_count": content_details.get("itemCount"),
        },
    }
