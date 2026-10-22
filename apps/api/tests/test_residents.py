from sqlalchemy import select

from app.models import AuditEvent
from tests.factories import auth

MANAGER = auth("manager.a@example.com")


def _base(world):
    return f"/v1/condominiums/{world.condo_a.id}/residents"


def _create(client, world, **body):
    payload = {"full_name": "Maria Silva", **body}
    return client.post(_base(world), json=payload, headers=MANAGER)


def test_create_resident_normalizes_phones_and_links_units(client, world):
    response = _create(
        client,
        world,
        phones=[{"number": "(11) 98765-4321"}, {"number": "+55 21 99876-5432"}],
        units=[{"unit_id": str(world.unit_a1.id), "relationship": "owner"}],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "invited"
    assert [(p["phone_e164"], p["is_primary"]) for p in body["phones"]] == [
        ("+5511987654321", True),
        ("+5521998765432", False),
    ]
    assert body["units"][0]["unit_id"] == str(world.unit_a1.id)
    assert body["units"][0]["relationship"] == "owner"


def test_audit_event_has_no_personal_data(client, db, world):
    resident = _create(client, world, phones=[{"number": "11987654321"}]).json()
    event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == resident["id"]))
    serialized = str(event.data)
    assert "Maria" not in serialized
    assert "98765" not in serialized
    assert event.actor_id == world.manager_a.id


def test_invalid_phone_is_422(client, world):
    response = _create(client, world, phones=[{"number": "12345678"}])
    assert response.status_code == 422


def test_phone_is_unique_within_condominium_only(client, world):
    assert _create(client, world, phones=[{"number": "11987654321"}]).status_code == 201
    duplicate = _create(client, world, full_name="Outra", phones=[{"number": "+5511987654321"}])
    assert duplicate.status_code == 409

    other_condo = client.post(
        f"/v1/condominiums/{world.condo_b.id}/residents",
        json={"full_name": "Maria Silva", "phones": [{"number": "11987654321"}]},
        headers=auth("manager.b@example.com"),
    )
    assert other_condo.status_code == 201


def test_suspend_and_reinstate_without_enrollment_returns_to_invited(client, world):
    resident = _create(client, world).json()
    url = f"{_base(world)}/{resident['id']}"
    assert client.post(f"{url}/suspend", headers=MANAGER).json()["status"] == "suspended"
    assert client.post(f"{url}/suspend", headers=MANAGER).status_code == 409
    assert client.post(f"{url}/reinstate", headers=MANAGER).json()["status"] == "invited"


def test_revoke_ends_units_removes_phones_and_is_final(client, world):
    resident = _create(
        client,
        world,
        phones=[{"number": "11987654321"}],
        units=[{"unit_id": str(world.unit_a1.id), "relationship": "tenant"}],
    ).json()
    url = f"{_base(world)}/{resident['id']}"

    assert client.post(f"{url}/revoke", headers=MANAGER).json()["status"] == "revoked"

    detail = client.get(url, headers=MANAGER).json()
    assert detail["phones"] == []
    assert all(m["ended_at"] is not None for m in detail["units"])
    assert client.patch(url, json={"full_name": "X"}, headers=MANAGER).status_code == 409
    assert client.post(f"{url}/reinstate", headers=MANAGER).status_code == 409
    # The freed number can be registered to a new record.
    assert _create(client, world, phones=[{"number": "11987654321"}]).status_code == 201


def test_unit_membership_can_be_ended_and_relinked(client, world):
    resident = _create(client, world).json()
    url = f"{_base(world)}/{resident['id']}/units"
    link = {"unit_id": str(world.unit_a1.id), "relationship": "tenant"}

    membership = client.post(url, json=link, headers=MANAGER).json()
    assert client.post(url, json=link, headers=MANAGER).status_code == 409
    ended = client.post(f"{url}/{membership['id']}/end", headers=MANAGER).json()
    assert ended["ended_at"] is not None
    assert client.post(url, json=link, headers=MANAGER).status_code == 201


def test_list_filters(client, world):
    _create(client, world, full_name="Ana 100% Souza")
    _create(
        client,
        world,
        full_name="Bruno Lima",
        units=[{"unit_id": str(world.unit_a1.id), "relationship": "owner"}],
    )

    def names(**params):
        r = client.get(_base(world), params=params, headers=MANAGER)
        return [i["full_name"] for i in r.json()["items"]]

    assert names() == ["Ana 100% Souza", "Bruno Lima"]
    assert names(q="bruno") == ["Bruno Lima"]
    assert names(q="%") == ["Ana 100% Souza"]  # wildcard is matched literally
    assert names(unit_id=str(world.unit_a1.id)) == ["Bruno Lima"]
