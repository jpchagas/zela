"""Turns a bearer token into a verified identity. Who that identity may act as is decided
later, against the database (see app.auth.dependencies and app.rbac)."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import Unauthenticated


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None = None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity: ...


class FirebaseTokenVerifier:
    def __init__(self, project_id: str | None):
        import firebase_admin

        # On Cloud Run this picks up the service account through Application Default Credentials.
        options = {"projectId": project_id} if project_id else None
        try:
            self._app = firebase_admin.get_app()
        except ValueError:
            self._app = firebase_admin.initialize_app(options=options)

    def verify(self, token: str) -> VerifiedIdentity:
        from firebase_admin import auth

        try:
            claims = auth.verify_id_token(token, app=self._app, check_revoked=True)
        except Exception as exc:  # the SDK raises several unrelated types
            raise Unauthenticated("Invalid or expired token") from exc
        return VerifiedIdentity(
            uid=claims["uid"],
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified")),
            name=claims.get("name"),
        )


class DevTokenVerifier:
    """Accepts `dev:<email>`. Settings refuse to enable this outside development/test."""

    def verify(self, token: str) -> VerifiedIdentity:
        prefix, _, email = token.partition(":")
        if prefix != "dev" or "@" not in email:
            raise Unauthenticated("Expected a dev token of the form dev:<email>")
        email = email.strip().lower()
        return VerifiedIdentity(uid=f"dev:{email}", email=email, email_verified=True)


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    if settings.auth_mode == "dev":
        return DevTokenVerifier()
    return FirebaseTokenVerifier(settings.firebase_project_id)
