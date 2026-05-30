from .youtube import YouTubeProvider
from .facebook import FacebookProvider
from .tiktok import TikTokProvider
from .pinterest import PinterestProvider

def get_provider(platform: str):
    platform = platform.lower().strip()
    providers = {
        "youtube": YouTubeProvider,
        "facebook": FacebookProvider,
        "tiktok": TikTokProvider,
        "pinterest": PinterestProvider,
    }
    if platform not in providers:
        raise ValueError(f"Unsupported platform: {platform}")
    return providers[platform]()
