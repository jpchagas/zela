from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.integrations.whatsapp.sender import RecordingSender, get_whatsapp_sender
from app.llm.scripted import ScriptedLLM, call, say
from app.main import app
from app.models import AuditEvent, Conversation
from tests.factories import auth
from tests.whatsapp import RESIDENT_PHONE, deliver, make_resident

MANAGER = auth("manager.a@example.com")


@pytest.fixture
def sender():
    s = RecordingSender()
    app.dependency_overrides[get_whatsapp_sender] = lambda: s
    return s


@pytest.fixture
def escalated(db, world, sender):
    make_resident(db, world.condo_a, unit=world.unit_a1)
    llm = ScriptedLLM(
        [call("escalate_to_human", reason="Vazamento na garagem"), say("Chamei a equipe.")]
    )
    deliver(db, world.condo_a, "tem um vazamento na garagem", sender=sender, llm=llm)
    return db.scalar(select(Conversation))


def _base(world):
    return f"/v1/condominiums/{world.condo_a.id}/conversations"


def test_manager_lists_and_reads_conversations(client, world, escalated):
    items = client.get(_base(world), params={"status": "escalated"}, headers=MANAGER).json()[
        "items"
    ]
    assert [(i["resident_name"], i["status"]) for i in items] == [("Maria Silva", "escalated")]
    assert items[0]["escalation_reason"] == "Vazamento na garagem"

    detail = client.get(f"{_base(world)}/{escalated.id}", headers=MANAGER).json()
    assert [m["kind"] for m in detail["messages"]] == ["resident", "ai_reply"]
    assert detail["can_reply"] is True
    assert detail["contact_e164"] == RESIDENT_PHONE


def test_front_desk_staff_cannot_read_conversations(client, world, escalated):
    assert client.get(_base(world), headers=auth("staff.a@example.com")).status_code == 403


def test_other_condominium_cannot_see_conversation(client, world, escalated):
    response = client.get(
        f"/v1/condominiums/{world.condo_b.id}/conversations/{escalated.id}",
        headers=auth("manager.b@example.com"),
    )
    assert response.status_code == 404


def test_staff_reply_is_sent_once_and_audited(client, db, world, sender, escalated):
    url = f"{_base(world)}/{escalated.id}/messages"
    body = {"body": "Olá Maria, o zelador já está indo.", "client_message_id": "abc12345"}
    first = client.post(url, json=body, headers=MANAGER)
    again = client.post(url, json=body, headers=MANAGER)

    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["kind"] == "staff_reply"
    assert first.json()["delivery_status"] == "sent"
    assert [s[2] for s in sender.sent][-1] == "Olá Maria, o zelador já está indo."
    assert sum(1 for s in sender.sent if s[2] == body["body"]) == 1
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "conversation.staff_replied"))


def test_reply_outside_24h_window_is_refused(client, db, world, escalated):
    escalated.last_inbound_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db.commit()
    response = client.post(
        f"{_base(world)}/{escalated.id}/messages",
        json={"body": "Oi", "client_message_id": "abc12345"},
        headers=MANAGER,
    )
    assert response.status_code == 409
    assert (
        client.get(f"{_base(world)}/{escalated.id}", headers=MANAGER).json()["can_reply"] is False
    )


def test_return_to_assistant(client, db, world, sender, escalated):
    url = f"{_base(world)}/{escalated.id}/return-to-assistant"
    assert client.post(url, headers=MANAGER).json()["status"] == "active"
    assert client.post(url, headers=MANAGER).status_code == 409

    # The assistant answers again.
    deliver(db, world.condo_a, "obrigada", sender=sender, llm=ScriptedLLM([say("De nada!")]))
    assert sender.sent[-1][2] == "De nada!"


def test_summary_counts_escalations(client, world, escalated):
    summary = client.get(f"/v1/condominiums/{world.condo_a.id}/summary", headers=MANAGER).json()
    assert summary["conversations_escalated"] == 1


def test_only_org_admins_configure_whatsapp(client, world):
    url = f"/v1/condominiums/{world.condo_a.id}/whatsapp"
    assert (
        client.put(url, json={"whatsapp_phone_number_id": "123456789"}, headers=MANAGER).status_code
        == 403
    )
    owner = auth("owner1@example.com")
    assert (
        client.put(url, json={"whatsapp_phone_number_id": "123456789"}, headers=owner).status_code
        == 200
    )
    taken = client.put(
        f"/v1/condominiums/{world.condo_b.id}/whatsapp",
        json={"whatsapp_phone_number_id": "123456789"},
        headers=owner,
    )
    assert taken.status_code == 409
    assert (
        client.put(url, json={"whatsapp_phone_number_id": "abc"}, headers=owner).status_code == 422
    )
