import time
import requests

from config import Config
from services.pinterest_oauth import get_valid_pinterest_access_token
from .base import BaseProvider, UploadResult


class PinterestProvider(BaseProvider):
    name = "pinterest"
    base_url = "https://api.pinterest.com/v5"

    def _headers(self):
        access_token = get_valid_pinterest_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def upload(self, job) -> UploadResult:
        board_id = job.destination_id or Config.PINTEREST_BOARD_ID
        if not board_id:
            return UploadResult(
                success=False,
                error="Choose a Pinterest board in the UI or set PINTEREST_BOARD_ID in .env",
            )

        try:
            # Step 1: register media upload.
            register = requests.post(
                f"{self.base_url}/media",
                headers=self._headers(),
                json={"media_type": "video"},
                timeout=60,
            )

            if not register.ok:
                return UploadResult(
                    success=False,
                    response=self._safe_json(register),
                    error=f"Pinterest media registration failed: HTTP {register.status_code}",
                )

            media_data = register.json()
            media_id = media_data.get("media_id")
            upload_url = media_data.get("upload_url")
            upload_params = media_data.get("upload_parameters", {})

            if not media_id or not upload_url:
                return UploadResult(
                    success=False,
                    response=media_data,
                    error="Pinterest media registration response missing media_id or upload_url.",
                )

            # Step 2: upload the file to the returned media bucket URL.
            with open(job.video_path, "rb") as video_file:
                files = {"file": video_file}
                upload_response = requests.post(
                    upload_url,
                    data=upload_params,
                    files=files,
                    timeout=900,
                )

            if upload_response.status_code not in (200, 201, 204):
                return UploadResult(
                    success=False,
                    error=(
                        "Pinterest media bucket upload failed: "
                        f"HTTP {upload_response.status_code}: {upload_response.text[:1000]}"
                    ),
                )

            # Step 3: poll media status.
            media_status = None
            for _ in range(30):
                status_response = requests.get(
                    f"{self.base_url}/media/{media_id}",
                    headers=self._headers(),
                    timeout=60,
                )
                media_status = self._safe_json(status_response)
                status_value = str(media_status.get("status", "")).lower()

                if status_value in {"succeeded", "success", "available"}:
                    break

                if status_value in {"failed", "failure"}:
                    return UploadResult(
                        success=False,
                        response=media_status,
                        error="Pinterest media processing failed.",
                    )

                time.sleep(10)

            # Step 4: create the Pin.
            pin_payload = {
                "board_id": board_id,
                "title": job.title[:100],
                "description": job.description or "",
                "media_source": {
                    "source_type": "video_id",
                    "media_id": media_id,
                },
            }

            pin_response = requests.post(
                f"{self.base_url}/pins",
                headers=self._headers(),
                json=pin_payload,
                timeout=60,
            )

            pin_data = self._safe_json(pin_response)
            if pin_response.ok:
                return UploadResult(
                    success=True,
                    external_id=pin_data.get("id"),
                    response=pin_data,
                )

            return UploadResult(
                success=False,
                response=pin_data,
                error=f"Pinterest create pin failed: HTTP {pin_response.status_code}",
            )

        except Exception as exc:
            return UploadResult(success=False, error=str(exc))

    @staticmethod
    def _safe_json(response):
        try:
            return response.json()
        except Exception:
            return {"raw": response.text[:1000] if response is not None else ""}
