from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.verifier import TokenVerifier, VerifiedIdentity, get_token_verifier
from app.core.errors import Forbidden, Unauthenticated
from app.db.session import get_db
from app.models import User
from app.models.enums import ActorType
from app.services import audit

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> User:
    if credentials is None:
        raise Unauthenticated("Missing bearer token")
    identity = verifier.verify(credentials.credentials)

    user = db.scalar(select(User).where(User.firebase_uid == identity.uid))
    if user is None:
        user = _link_invited_user(db, identity)
    if user.disabled_at is not None:
        raise Forbidden("Account disabled")
    return user


def _link_invited_user(db: Session, identity: VerifiedIdentity) -> User:
    """Dashboard access is invite-only: a first sign-in is accepted only when its verified
    email matches a user someone already invited."""
    if not (identity.email and identity.email_verified):
        raise Forbidden("Account not provisioned")
    user = db.scalar(
        select(User).where(
            func.lower(User.email) == identity.email.lower(), User.firebase_uid.is_(None)
        )
    )
    if user is None:
        raise Forbidden("Account not provisioned")

    user.firebase_uid = identity.uid
    if identity.name and not user.display_name:
        user.display_name = identity.name
    audit.record(
        db,
        organization_id=None,
        condominium_id=None,
        actor_type=ActorType.USER,
        actor_id=user.id,
        action="user.identity_linked",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    return user
