import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask
from google_auth_oauthlib.flow import InstalledAppFlow

from config import Config
from models import db
from services.youtube_oauth import (
    YOUTUBE_SCOPES,
    get_authenticated_youtube_channels,
    save_credentials_for_channels,
)


def main():
    client_secret = Path(Config.YOUTUBE_CLIENT_SECRET_FILE)

    if not client_secret.exists():
        raise FileNotFoundError(
            f"Missing {client_secret}. Download your OAuth client JSON from Google Cloud."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret),
        scopes=YOUTUBE_SCOPES,
    )

    credentials = flow.run_local_server(
        host="localhost",
        port=5001,
        open_browser=True,
        access_type="offline",
        prompt="consent select_account",
        authorization_prompt_message="Please visit this URL to authorize YouTube access: {url}",
        success_message="YouTube authorization completed. You can close this browser tab.",
    )

    channels = get_authenticated_youtube_channels(credentials)

    app = Flask(
        __name__,
        instance_path=str(PROJECT_ROOT / "instance"),
    )
    app.config.from_object(Config)

    with app.app_context():
        db.init_app(app)
        db.create_all()
        saved_channels = save_credentials_for_channels(credentials, channels)

    print("Saved YouTube token and cached channel destination(s):")
    for channel in saved_channels:
        token_file = (channel.get("extra") or {}).get("token_file")
        print(f"- {channel['name']} ({channel['id']}) -> {token_file}")

    print()
    print(
        "If you manage more channels, run this script again and pick the next "
        "channel/Brand Account in Google's authorization screen."
    )


if __name__ == "__main__":
    main()
