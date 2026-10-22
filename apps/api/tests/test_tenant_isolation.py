"""Cross-tenant access must be impossible (PDD §13.10). Foreign resources answer 404, the
same as nonexistent ones, so IDs can't be probed."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Resident, StaffMembership
from tests.factories import auth


def _resident(client, condo_id, email, **extra):
    body = {"full_name": "Maria Silva", "phones": [{"number": "11987654321"}], **extra}
    response = client.post(f"/v1/condominiums/{condo_id}/residents", json=body, headers=auth(email))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "email,condo_attr",
    [
        ("manager.a@example.com", "condo_b"),  # same org, other condominium
        ("manager.a@example.com", "condo_c"),  # other org
        ("owner2@example.com", "condo_a"),  # org owner, other org
        ("owner1@example.com", "condo_c"),
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        "",
        "/summary",
        "/buildings",
        "/units",
        "/residents",
        "/staff",
        "/conversations",
        "/audit-events",
    ],
)
def test_foreign_condominium_reads_are_404(client, world, email, condo_attr, path):
    condo = getattr(world, condo_attr)
    response = client.get(f"/v1/condominiums/{condo.id}{path}", headers=auth(email))
    assert response.status_code == 404


def test_nonexistent_condominium_looks_the_same_as_foreign(client, world):
    foreign = client.get(f"/v1/condominiums/{world.condo_c.id}", headers=auth("owner1@example.com"))
    missing = client.get(f"/v1/condominiums/{uuid.uuid4()}", headers=auth("owner1@example.com"))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_org_owner_reaches_every_condominium_in_their_org(client, world):
    for condo in (world.condo_a, world.condo_b):
        response = client.get(f"/v1/condominiums/{condo.id}", headers=auth("owner1@example.com"))
        assert response.status_code == 200


def test_foreign_writes_are_404_and_create_nothing(client, db, world):
    response = client.post(
        f"/v1/condominiums/{world.condo_b.id}/residents",
        json={"full_name": "Intruso"},
        headers=auth("manager.a@example.com"),
    )
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(Resident)) == 0


def test_resident_of_other_condominium_is_404_through_own_condominium(client, world):
    resident_b = _resident(client, world.condo_b.id, "manager.b@example.com")
    response = client.get(
        f"/v1/condominiums/{world.condo_a.id}/residents/{resident_b['id']}",
        headers=auth("manager.a@example.com"),
    )
    assert response.status_code == 404


def test_cannot_link_resident_to_unit_of_other_condominium(client, db, world):
    response = client.post(
        f"/v1/condominiums/{world.condo_a.id}/residents",
        json={
            "full_name": "Maria Silva",
            "units": [{"unit_id": str(world.unit_b1.id), "relationship": "owner"}],
        },
        headers=auth("manager.a@example.com"),
    )
    assert response.status_code == 404
    # The flushed resident row must not survive the failed request.
    assert db.scalar(select(func.count()).select_from(Resident)) == 0


def test_cannot_create_unit_in_building_of_other_condominium(client, db, world):
    building_b = client.get(
        f"/v1/condominiums/{world.condo_b.id}/buildings", headers=auth("manager.b@example.com")
    ).json()[0]
    response = client.post(
        f"/v1/condominiums/{world.condo_a.id}/units",
        json={"building_id": building_b["id"], "identifier": "999"},
        headers=auth("manager.a@example.com"),
    )
    assert response.status_code == 404


def test_audit_log_shows_only_own_condominium(client, world):
    _resident(client, world.condo_a.id, "manager.a@example.com")
    _resident(client, world.condo_b.id, "manager.b@example.com")
    events = client.get(
        f"/v1/condominiums/{world.condo_a.id}/audit-events", headers=auth("manager.a@example.com")
    ).json()["items"]
    assert events
    assert {e["action"] for e in events} == {"resident.created"}
    assert len(events) == 1


def test_revoked_staff_membership_loses_access(client, db, world):
    membership = db.scalar(
        select(StaffMembership).where(StaffMembership.user_id == world.manager_a.id)
    )
    membership.revoked_at = datetime.now(timezone.utc)
    db.commit()
    response = client.get(
        f"/v1/condominiums/{world.condo_a.id}", headers=auth("manager.a@example.com")
    )
    assert response.status_code == 404


def test_staff_role_cannot_read_resident_directory(client, world):
    response = client.get(
        f"/v1/condominiums/{world.condo_a.id}/residents", headers=auth("staff.a@example.com")
    )
    assert response.status_code == 403


def test_staff_role_can_read_units_but_not_change_them(client, world):
    base = f"/v1/condominiums/{world.condo_a.id}/units"
    assert client.get(base, headers=auth("staff.a@example.com")).status_code == 200
    response = client.post(base, json={"identifier": "102"}, headers=auth("staff.a@example.com"))
    assert response.status_code == 403
