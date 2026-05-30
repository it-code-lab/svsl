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

    FACEBOOK_GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v25.0")
    FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
    FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")

    TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")
