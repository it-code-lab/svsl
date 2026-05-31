from datetime import timedelta

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from services.datetime_utils import ensure_utc_required, utc_now
from services.youtube_oauth import YOUTUBE_SCOPES, get_youtube_credentials_for_channel
from .base import BaseProvider, UploadResult


class YouTubeProvider(BaseProvider):
    name = "youtube"
    supports_native_schedule = True

    def _client(self, channel_id=None):
        creds = get_youtube_credentials_for_channel(channel_id)
        return build("youtube", "v3", credentials=creds)

    @staticmethod
    def _parse_tags(tags: str):
        if not tags:
            return []
        return [t.strip().lstrip("#") for t in tags.replace("\n", ",").split(",") if t.strip()]

    def upload(self, job) -> UploadResult:
        try:
            youtube = self._client(job.destination_id)

            scheduled_dt = ensure_utc_required(job.scheduled_at_utc, "scheduled_at_utc")
            now = utc_now()

            status_body = {
                "selfDeclaredMadeForKids": False,
            }

            # If scheduled time is meaningfully in the future, use YouTube's native scheduling.
            # If the user chose "now" or a time too close to now, publish immediately.
            if scheduled_dt > now + timedelta(minutes=2):
                publish_at = scheduled_dt.isoformat().replace("+00:00", "Z")
                status_body.update(
                    {
                        "privacyStatus": "private",
                        "publishAt": publish_at,
                    }
                )
            else:
                status_body.update(
                    {
                        "privacyStatus": "public",
                    }
                )

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
