from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from config import Config
from providers.youtube import YOUTUBE_SCOPES


def main():
    client_secret = Path(Config.YOUTUBE_CLIENT_SECRET_FILE)
    token_file = Path(Config.YOUTUBE_TOKEN_FILE)
    token_file.parent.mkdir(parents=True, exist_ok=True)

    if not client_secret.exists():
        raise FileNotFoundError(
            f"Missing {client_secret}. Download your OAuth client JSON from Google Cloud."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret),
        scopes=YOUTUBE_SCOPES,
    )
    credentials = flow.run_local_server(port=0)

    token_file.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Saved YouTube token to {token_file}")


if __name__ == "__main__":
    main()
