from app.integrations.whatsapp.sender import RecordingSender
from app.workers import inbound as msgs
from tests.factories import auth
from tests.whatsapp import deliver, outbound

MANAGER = auth("manager.a@example.com")


def _url(world):
    return f"/v1/condominiums/{world.condo_a.id}/emergency-contacts"


def test_manage_on_call_contacts(client, world):
    created = client.post(
        _url(world),
        json={"name": "Zelador", "role": "Plantão noturno", "phone": "(11) 93333-0001"},
        headers=MANAGER,
    )
    assert created.status_code == 201 and created.json()["phone_e164"] == "+5511933330001"
    assert (
        client.post(
            _url(world), json={"name": "Outro", "phone": "11933330001"}, headers=MANAGER
        ).status_code
        == 409
    )
    assert (
        client.post(_url(world), json={"name": "X", "phone": "123"}, headers=MANAGER).status_code
        == 422
    )
    assert [c["name"] for c in client.get(_url(world), headers=MANAGER).json()] == ["Zelador"]
    assert (
        client.delete(f"{_url(world)}/{created.json()['id']}", headers=MANAGER).status_code == 204
    )


def test_front_desk_cannot_manage_contacts(client, world):
    assert client.get(_url(world), headers=auth("staff.a@example.com")).status_code == 403


def test_on_call_contact_writing_in_gets_an_acknowledgement(client, db, world):
    client.post(_url(world), json={"name": "Zelador", "phone": "11933330001"}, headers=MANAGER)
    deliver(
        db, world.condo_a, "ok, estou indo", sender=RecordingSender(), from_e164="+5511933330001"
    )
    assert outbound(db)[0].body == msgs.ON_CALL_ACK.format(condo="Residencial Aurora")
