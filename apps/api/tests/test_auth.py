import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.verifier import VerifiedIdentity, get_token_verifier
from app.core.config import Settings
from app.main import app
from app.models import AuditEvent, StaffMembership
from app.models.enums import StaffRole
from tests.factories import auth, make_user


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_missing_token_is_401(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_malformed_dev_token_is_401(client):
    assert client.get("/v1/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_unknown_identity_is_not_provisioned(client, world):
    response = client.get("/v1/me", headers=auth("stranger@example.com"))
    assert response.status_code == 403


def test_invited_user_is_linked_on_first_sign_in(client, db, world):
    invited = make_user(db, "Invited@Example.com", linked=False)
    db.add(
        StaffMembership(user_id=invited.id, condominium_id=world.condo_a.id, role=StaffRole.STAFF)
    )
    db.commit()

    response = client.get("/v1/me", headers=auth("invited@example.com"))

    assert response.status_code == 200
    assert [c["condominium_id"] for c in response.json()["condominiums"]] == [str(world.condo_a.id)]
    db.refresh(invited)
    assert invited.firebase_uid == "dev:invited@example.com"
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "user.identity_linked", AuditEvent.entity_id == invited.id
        )
    )


def test_unverified_email_is_not_linked(client, db, world):
    make_user(db, "unverified@example.com", linked=False)
    db.commit()

    class UnverifiedVerifier:
        def verify(self, token):
            return VerifiedIdentity(
                uid="fb-123", email="unverified@example.com", email_verified=False
            )

    app.dependency_overrides[get_token_verifier] = UnverifiedVerifier
    response = client.get("/v1/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403


def test_disabled_user_is_rejected(client, db, world):
    from datetime import datetime, timezone

    world.manager_a.disabled_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get("/v1/me", headers=auth("manager.a@example.com")).status_code == 403


def test_dev_auth_is_refused_outside_development():
    with pytest.raises(ValidationError):
        Settings(env="production", auth_mode="dev")


def test_me_lists_only_accessible_condominiums(client, world):
    owner = client.get("/v1/me", headers=auth("owner1@example.com")).json()
    assert {(c["condominium_name"], c["role"]) for c in owner["condominiums"]} == {
        ("Residencial Aurora", "org_owner"),
        ("Edifício Bela Vista", "org_owner"),
    }

    manager = client.get("/v1/me", headers=auth("manager.a@example.com")).json()
    assert [(c["condominium_name"], c["role"]) for c in manager["condominiums"]] == [
        ("Residencial Aurora", "manager")
    ]
