from config import Config
from .base import BaseProvider, UploadResult


class TikTokProvider(BaseProvider):
    name = "tiktok"

    def upload(self, job) -> UploadResult:
        # TikTok Direct Post requires:
        # - A registered TikTok developer app
        # - Content Posting API product added
        # - App review/approval
        # - OAuth scope such as video.publish or video.upload
        #
        # Because every approved TikTok app must follow TikTok's creator-info
        # and posting UX requirements, this starter records a clear status
        # instead of pretending a universal token-only upload will work.
        if not Config.TIKTOK_ACCESS_TOKEN:
            return UploadResult(
                success=False,
                error=(
                    "TikTok provider is a skeleton. Add your approved Content Posting API "
                    "implementation and TIKTOK_ACCESS_TOKEN."
                ),
            )

        return UploadResult(
            success=False,
            error=(
                "TikTok Direct Post implementation is intentionally left as a provider "
                "extension point. Implement /v2/post/publish/creator_info/query/ and "
                "/v2/post/publish/video/init/ using your approved TikTok app."
            ),
        )
