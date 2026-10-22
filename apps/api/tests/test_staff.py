from tests.factories import auth

MANAGER = auth("manager.a@example.com")
OWNER = auth("owner1@example.com")


def _url(world):
    return f"/v1/condominiums/{world.condo_a.id}/staff"


def test_manager_can_invite_staff_but_not_managers(client, world):
    staff = client.post(
        _url(world), json={"email": "porteiro@example.com", "role": "staff"}, headers=MANAGER
    )
    assert staff.status_code == 201
    assert staff.json()["has_signed_in"] is False

    manager = client.post(
        _url(world), json={"email": "sub@example.com", "role": "manager"}, headers=MANAGER
    )
    assert manager.status_code == 403


def test_org_owner_can_appoint_manager(client, world):
    response = client.post(
        _url(world), json={"email": "sub@example.com", "role": "manager"}, headers=OWNER
    )
    assert response.status_code == 201


def test_duplicate_invite_is_conflict(client, world):
    body = {"email": "Porteiro@Example.com", "role": "staff"}
    assert client.post(_url(world), json=body, headers=MANAGER).status_code == 201
    assert client.post(_url(world), json=body, headers=MANAGER).status_code == 409


def test_invited_staff_signs_in_and_then_loses_access_when_revoked(client, world):
    invite = client.post(
        _url(world), json={"email": "porteiro@example.com", "role": "staff"}, headers=MANAGER
    ).json()
    porteiro = auth("porteiro@example.com")

    me = client.get("/v1/me", headers=porteiro).json()
    assert [(c["condominium_name"], c["role"]) for c in me["condominiums"]] == [
        ("Residencial Aurora", "staff")
    ]

    assert (
        client.delete(f"{_url(world)}/{invite['membership_id']}", headers=MANAGER).status_code
        == 204
    )
    assert client.get(f"/v1/condominiums/{world.condo_a.id}", headers=porteiro).status_code == 404


def test_staff_cannot_manage_staff(client, world):
    body = {"email": "x@example.com", "role": "staff"}
    assert (
        client.post(_url(world), json=body, headers=auth("staff.a@example.com")).status_code == 403
    )
