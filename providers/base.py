from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class UploadResult:
    success: bool
    external_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BaseProvider:
    name = "base"

    # True means: upload to the platform now and ask the platform to publish later.
    # False means: keep the job in this app until scheduled_at_utc, then publish.
    supports_native_schedule = False

    # Optional platform limits. Facebook, for example, only accepts scheduled
    # publish times inside a limited future window.
    native_schedule_min_seconds = 0
    native_schedule_max_seconds = None

    def upload(self, job) -> UploadResult:
        raise NotImplementedError
