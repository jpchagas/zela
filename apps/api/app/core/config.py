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
    # "meta" sends through the Cloud API; "log" only records outbound messages (local dev).
    whatsapp_sender: Literal["meta", "log"] = "meta"
    whatsapp_access_token: str = ""
    whatsapp_graph_version: str = "v23.0"

    # Keys HMACs of enrollment codes. Must be a long random value outside development.
    secret_key: str = "dev-insecure-secret-key"

    # "anthropic" calls the Claude API (ANTHROPIC_API_KEY is read by the SDK);
    # "scripted" is a canned responder for local runs without an API key.
    llm_provider: Literal["anthropic", "scripted"] = "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_timeout_seconds: float = 45.0

    # "inline" runs jobs in a thread pool inside the API process (local dev and tests).
    # Pub/Sub push delivery arrives with the deployment milestone.
    jobs_mode: Literal["inline", "log"] = "inline"

    @model_validator(mode="after")
    def _dev_auth_only_in_development(self) -> "Settings":
        # The dev verifier trusts any email it is given; it must never reach a deployed env.
        if self.auth_mode == "dev" and self.env not in ("development", "test"):
            raise ValueError("AUTH_MODE=dev is only allowed when ENV is development or test")
        if self.env in ("staging", "production") and (
            self.secret_key == "dev-insecure-secret-key" or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
