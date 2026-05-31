_PROVIDER_CLASS_NAMES = {
    "youtube": "YouTubeProvider",
    "facebook": "FacebookProvider",
    "tiktok": "TikTokProvider",
    "pinterest": "PinterestProvider",
}


def __getattr__(name: str):
    if name == "YouTubeProvider":
        from .youtube import YouTubeProvider

        return YouTubeProvider

    if name == "FacebookProvider":
        from .facebook import FacebookProvider

        return FacebookProvider

    if name == "TikTokProvider":
        from .tiktok import TikTokProvider

        return TikTokProvider

    if name == "PinterestProvider":
        from .pinterest import PinterestProvider

        return PinterestProvider

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_provider(platform: str):
    platform = platform.lower().strip()

    provider_class_name = _PROVIDER_CLASS_NAMES.get(platform)
    if provider_class_name:
        return __getattr__(provider_class_name)()

    raise ValueError(f"Unsupported platform: {platform}")


__all__ = [
    "get_provider",
    "YouTubeProvider",
    "FacebookProvider",
    "TikTokProvider",
    "PinterestProvider",
]
