import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///scheduler.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "2048")) * 1024 * 1024
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Montreal")

    ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
    SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))
    ADMIN_RUN_KEY = os.getenv("ADMIN_RUN_KEY", "change-me")

    YOUTUBE_CLIENT_SECRET_FILE = os.getenv(
        "YOUTUBE_CLIENT_SECRET_FILE",
        "instance/youtube_client_secret.json",
    )
    YOUTUBE_TOKEN_FILE = os.getenv(
        "YOUTUBE_TOKEN_FILE",
        "instance/youtube_token.json",
    )
    YOUTUBE_TOKEN_DIR = os.getenv(
        "YOUTUBE_TOKEN_DIR",
        "instance/youtube_tokens",
    )

    FACEBOOK_GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v25.0")

    # Facebook OAuth configuration for pulling Pages dynamically.
    # Use Meta Developer App > Facebook Login > Valid OAuth Redirect URIs.
    FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
    FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")
    FACEBOOK_REDIRECT_URI = os.getenv(
        "FACEBOOK_REDIRECT_URI",
        "http://127.0.0.1:5001/oauth/facebook/callback",
    )
    FACEBOOK_SCOPES = os.getenv(
        "FACEBOOK_SCOPES",
        "pages_show_list,pages_read_engagement,pages_manage_posts",
    )

    # Backward-compatible fallback for a single Page setup.
    # Dynamic page selection uses cached pages from /me/accounts instead.
    FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
    FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")

    DESTINATION_CACHE_TTL_MINUTES = int(os.getenv("DESTINATION_CACHE_TTL_MINUTES", "360"))

    TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    # Pinterest OAuth configuration.
    # Use the values from Pinterest Developer Platform > Your App > Configure.
    PINTEREST_CLIENT_ID = os.getenv("PINTEREST_CLIENT_ID", "")
    PINTEREST_CLIENT_SECRET = os.getenv("PINTEREST_CLIENT_SECRET", "")
    PINTEREST_REDIRECT_URI = os.getenv(
        "PINTEREST_REDIRECT_URI",
        "http://127.0.0.1:5001/oauth/pinterest/callback",
    )
    PINTEREST_SCOPES = os.getenv(
        "PINTEREST_SCOPES",
        "pins:read,pins:write,boards:read",
    )
    PINTEREST_CONTINUOUS_REFRESH = os.getenv(
        "PINTEREST_CONTINUOUS_REFRESH",
        "true",
    ).lower() == "true"

    # Keep this as the target board for created Pins.
    # Later you can add a board picker using boards:read.
    PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")

    # Kept only for backward compatibility/testing. The provider now prefers
    # the OAuth token stored in the database.
    PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")
