from functools import lru_cache

from app.core.config import get_settings
from app.integrations.google.base import Google


@lru_cache
def get_google() -> Google:
    settings = get_settings()
    if settings.google_mode == "fake":
        from app.integrations.google.fake import FakeGoogle

        return FakeGoogle(redirect_uri=settings.google_redirect_uri)
    from app.integrations.google.client import GoogleClient

    return GoogleClient(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )
