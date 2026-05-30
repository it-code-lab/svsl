import json
from pathlib import Path
from datetime import timezone, datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import Config
from .base import BaseProvider, UploadResult


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class YouTubeProvider(BaseProvider):
    name = "youtube"
    supports_native_schedule = True

    def _client(self):
        token_file = Path(Config.YOUTUBE_TOKEN_FILE)
        if not token_file.exists():
            raise RuntimeError(
                f"YouTube token file not found: {token_file}. "
                "Run scripts/youtube_auth.py first."
            )

        creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)
        return build("youtube", "v3", credentials=creds)

    @staticmethod
    def _parse_tags(tags: str):
        if not tags:
            return []
        return [t.strip().lstrip("#") for t in tags.replace("\n", ",").split(",") if t.strip()]

    def upload(self, job) -> UploadResult:
        try:
            youtube = self._client()

            scheduled_dt = job.scheduled_at_utc.astimezone(timezone.utc)
            now = datetime.now(timezone.utc)

            status_body = {
                "selfDeclaredMadeForKids": False,
            }

            # If scheduled time is meaningfully in the future, use YouTube's native scheduling.
            # If the user chose "now" or a time too close to now, publish immediately.
            if scheduled_dt > now + timedelta(minutes=2):
                publish_at = scheduled_dt.isoformat().replace("+00:00", "Z")
                status_body.update({
                    "privacyStatus": "private",
                    "publishAt": publish_at,
                })
            else:
                status_body.update({
                    "privacyStatus": "public",
                })

            body = {
                "snippet": {
                    "title": job.title,
                    "description": job.description or "",
                    "tags": self._parse_tags(job.tags),
                },
                "status": status_body,
            }

            media = MediaFileUpload(
                job.video_path,
                chunksize=1024 * 1024 * 8,
                resumable=True,
                mimetype="video/*",
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()

            video_id = response.get("id")

            if job.thumbnail_path and video_id:
                thumb_media = MediaFileUpload(job.thumbnail_path, mimetype="image/*", resumable=False)
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media,
                ).execute()

            # In this starter, playlist is expected to be a YouTube playlist ID.
            # Playlist title lookup/creation can be added later.
            if job.playlist and video_id:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": job.playlist.strip(),
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        }
                    },
                ).execute()

            return UploadResult(success=True, external_id=video_id, response=response)

        except Exception as exc:
            return UploadResult(success=False, error=str(exc))
