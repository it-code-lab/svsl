from datetime import datetime, timezone, timedelta

import requests
from config import Config
from services.facebook_oauth import get_facebook_page_destination
from .base import BaseProvider, UploadResult


class FacebookProvider(BaseProvider):
    name = "facebook"
    supports_native_schedule = True
    native_schedule_min_seconds = 10 * 60
    native_schedule_max_seconds = 30 * 24 * 60 * 60

    def upload(self, job) -> UploadResult:
        try:
            destination = get_facebook_page_destination(job.destination_id)
            page_id = destination["page_id"]
            page_access_token = destination["page_access_token"]
        except Exception as exc:
            return UploadResult(success=False, error=str(exc))

        # Meta video uploads use graph-video.facebook.com.
        url = (
            f"https://graph-video.facebook.com/{Config.FACEBOOK_GRAPH_VERSION}/"
            f"{page_id}/videos"
        )

        scheduled_dt = job.scheduled_at_utc.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)

        params = {
            "access_token": page_access_token,
            "title": job.title,
            "description": job.description or "",
        }

        # Facebook native scheduling only accepts a future window.
        # If the date is within the valid future window, schedule remotely.
        # If the due time has arrived or is too close, publish immediately.
        if scheduled_dt > now + timedelta(seconds=self.native_schedule_min_seconds):
            if scheduled_dt > now + timedelta(seconds=self.native_schedule_max_seconds):
                return UploadResult(
                    success=False,
                    error="Facebook scheduled_publish_time is more than 30 days away. The app will retry later when it is inside Facebook's scheduling window.",
                )

            params["published"] = "false"
            params["scheduled_publish_time"] = str(int(scheduled_dt.timestamp()))
        else:
            params["published"] = "true"

        try:
            with open(job.video_path, "rb") as video_file:
                files = {
                    "source": video_file,
                }
                response = requests.post(url, data=params, files=files, timeout=600)

            data = response.json() if response.content else {}
            if response.ok:
                return UploadResult(
                    success=True,
                    external_id=data.get("id"),
                    response={**data, "page_id": page_id, "page_name": destination.get("page_name")},
                )

            return UploadResult(
                success=False,
                response=data,
                error=f"Facebook upload failed: HTTP {response.status_code}: {data}",
            )

        except Exception as exc:
            return UploadResult(success=False, error=str(exc))
