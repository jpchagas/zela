from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "postgresql+psycopg://zela:zela@localhost:5433/zela"

    auth_mode: Literal["firebase", "dev"] = "firebase"
    firebase_project_id: str | None = None

    cors_origins: str = "http://localhost:3000"

    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    @model_validator(mode="after")
    def _dev_auth_only_in_development(self) -> "Settings":
        # The dev verifier trusts any email it is given; it must never reach a deployed env.
        if self.auth_mode == "dev" and self.env not in ("development", "test"):
            raise ValueError("AUTH_MODE=dev is only allowed when ENV is development or test")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
