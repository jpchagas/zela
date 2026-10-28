from tests.factories import auth

MANAGER = auth("manager.a@example.com")


def test_building_names_are_unique_per_condominium(client, world):
    url = f"/v1/condominiums/{world.condo_a.id}/buildings"
    assert client.post(url, json={"name": "Bloco A"}, headers=MANAGER).status_code == 409
    assert client.post(url, json={"name": "Bloco B"}, headers=MANAGER).status_code == 201


def test_unit_identifier_unique_per_building_including_no_building(client, world):
    url = f"/v1/condominiums/{world.condo_a.id}/units"
    dup = {"building_id": str(world.building_a.id), "identifier": "101"}
    assert client.post(url, json=dup, headers=MANAGER).status_code == 409

    assert client.post(url, json={"identifier": "Casa 1"}, headers=MANAGER).status_code == 201
    assert client.post(url, json={"identifier": "Casa 1"}, headers=MANAGER).status_code == 409


def test_building_with_units_cannot_be_deleted(client, world):
    url = f"/v1/condominiums/{world.condo_a.id}/buildings/{world.building_a.id}"
    assert client.delete(url, headers=MANAGER).status_code == 409


def test_update_condominium_records_changed_fields(client, world):
    response = client.patch(
        f"/v1/condominiums/{world.condo_a.id}",
        json={"city": "São Paulo", "state": "SP"},
        headers=MANAGER,
    )
    assert response.status_code == 200
    events = client.get(
        f"/v1/condominiums/{world.condo_a.id}/audit-events", headers=MANAGER
    ).json()["items"]
    assert events[0]["action"] == "condominium.updated"
    assert events[0]["data"] == {"fields": ["city", "state"]}


def test_only_org_admins_create_condominiums(client, world):
    url = f"/v1/organizations/{world.org1.id}/condominiums"
    body = {"name": "Novo Condomínio"}
    assert client.post(url, json=body, headers=MANAGER).status_code == 404
    assert client.post(url, json=body, headers=auth("owner2@example.com")).status_code == 404
    created = client.post(url, json=body, headers=auth("owner1@example.com"))
    assert created.status_code == 201
    assert created.json()["organization_id"] == str(world.org1.id)


def test_summary_counts_only_own_condominium(client, world):
    client.post(
        f"/v1/condominiums/{world.condo_b.id}/residents",
        json={"full_name": "Fora"},
        headers=auth("manager.b@example.com"),
    )
    response = client.get(
        f"/v1/condominiums/{world.condo_a.id}/summary", headers=auth("staff.a@example.com")
    )
    assert response.status_code == 200
    assert response.json() == {
        "buildings": 1,
        "units": 1,
        "residents_by_status": {"invited": 0, "active": 0, "suspended": 0, "revoked": 0},
        "staff": 2,
        "conversations_escalated": 0,
        "tickets_open": 0,
        "tickets_emergency_open": 0,
        "documents_failed": 0,
    }


def test_units_sort_by_building_name_then_identifier(client, db, world):
    from app.models import Building, Unit

    zeta = Building(condominium_id=world.condo_a.id, name="Bloco Z")
    db.add(zeta)
    db.flush()
    db.add_all(
        [
            Unit(condominium_id=world.condo_a.id, building_id=zeta.id, identifier="1"),
            Unit(
                condominium_id=world.condo_a.id, building_id=world.building_a.id, identifier="1001"
            ),
            Unit(condominium_id=world.condo_a.id, building_id=world.building_a.id, identifier="99"),
        ]
    )
    db.commit()
    items = client.get(f"/v1/condominiums/{world.condo_a.id}/units", headers=MANAGER).json()[
        "items"
    ]
    assert [u["identifier"] for u in items] == ["99", "101", "1001", "1"]
