import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import ScriptedLLM, call, say
from app.models import (
    Conversation,
    EmergencyContact,
    MaintenanceTicket,
    NotificationEvent,
    TicketEvent,
    Unit,
    UnitMembership,
)
from app.models.enums import (
    ConversationStatus,
    DeliveryStatus,
    MessageKind,
    TicketCategory,
    TicketPriority,
    UnitRelationship,
)
from app.services import notifications, tickets
from tests.factories import auth
from tests.whatsapp import RESIDENT_PHONE, deliver, make_resident, outbound

MANAGER = auth("manager.a@example.com")


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def maria(db, world):
    return make_resident(db, world.condo_a, unit=world.unit_a1)


def _report(db, world, sender, publisher, *args_list, message="o portão quebrou"):
    """Have the scripted model call create_maintenance_ticket with each args dict."""
    script = [call("create_maintenance_ticket", **args) for args in args_list]
    script.append(lambda s: say(s.outcomes[-1].content))
    llm = ScriptedLLM(script)
    deliver(db, world.condo_a, message, sender=sender, llm=llm, publisher=publisher)
    return [
        json.loads(o.content) if not o.is_error else o.content for o in llm.sessions[0].outcomes
    ]


GATE = {
    "title": "Portão da garagem não abre",
    "description": "O portão da saída da garagem parou de funcionar.",
    "location": "Garagem, portão de saída",
    "in_own_unit": False,
    "category": "gates_access",
    "priority": "high",
}


# --- Deterministic classification ------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Sinto um cheiro de gás forte no corredor",
        "tem FUMAÇA saindo do quadro de luz",
        "a garagem está alagada",
        "minha filha ficou presa no elevador",
        "um morador caiu e está ferido",
    ],
)
def test_emergency_keywords_force_emergency(text):
    decided = tickets.classify(text, TicketCategory.OTHER, TicketPriority.LOW)
    assert decided.priority == TicketPriority.EMERGENCY and decided.emergency_by_rule


def test_model_suggestion_is_used_otherwise_and_can_raise_to_emergency():
    assert (
        tickets.classify("lâmpada queimada", TicketCategory.ELECTRICAL, TicketPriority.LOW).priority
        == TicketPriority.LOW
    )
    assert (
        tickets.classify("portão travado", TicketCategory.GATES_ACCESS, None).priority
        == TicketPriority.NORMAL
    )
    raised = tickets.classify(
        "barulho estranho na caixa d'água", TicketCategory.PLUMBING, TicketPriority.EMERGENCY
    )
    assert raised.priority == TicketPriority.EMERGENCY and not raised.emergency_by_rule
    assert tickets.classify("x", None, None).category == TicketCategory.OTHER


# --- Created through the concierge ---------------------------------------------------------


def test_resident_reports_common_area_problem(db, world, sender, publisher, maria):
    [result] = _report(db, world, sender, publisher, GATE)
    assert result["reference"] == "#1"
    ticket = db.scalar(select(MaintenanceTicket))
    assert (ticket.category, ticket.priority, ticket.unit_id) == (
        TicketCategory.GATES_ACCESS,
        TicketPriority.HIGH,
        None,
    )
    assert ticket.ai_suggested_priority == TicketPriority.HIGH
    assert ticket.reporter_resident_id == maria.id
    assert ticket.conversation_id == db.scalar(select(Conversation.id))
    assert db.scalar(select(TicketEvent.event_type)) == "created"


def test_ticket_numbers_are_sequential_per_condominium(db, world, sender, publisher, maria):
    _report(db, world, sender, publisher, GATE, {**GATE, "title": "Lâmpada do hall queimada"})
    bob = make_resident(db, world.condo_b, phone="+5511955554444", unit=world.unit_b1)
    llm = ScriptedLLM([call("create_maintenance_ticket", **GATE), say("ok")])
    deliver(
        db,
        world.condo_b,
        "portão",
        sender=sender,
        llm=llm,
        publisher=publisher,
        from_e164="+5511955554444",
    )
    numbers = db.execute(select(MaintenanceTicket.condominium_id, MaintenanceTicket.number)).all()
    assert sorted(n for c, n in numbers if c == world.condo_a.id) == [1, 2]
    assert [n for c, n in numbers if c == world.condo_b.id] == [1]
    assert bob is not None


def test_own_unit_is_filled_in_and_ambiguity_is_asked(db, world, sender, publisher, maria):
    leak = {
        **GATE,
        "title": "Vazamento na pia",
        "in_own_unit": True,
        "location": None,
        "category": "plumbing",
        "priority": "normal",
    }
    [result] = _report(db, world, sender, publisher, leak)
    assert db.scalar(select(MaintenanceTicket.unit_id)) == world.unit_a1.id

    second = Unit(
        condominium_id=world.condo_a.id, building_id=world.building_a.id, identifier="202"
    )
    db.add(second)
    db.flush()
    db.add(
        UnitMembership(
            condominium_id=world.condo_a.id,
            unit_id=second.id,
            resident_id=maria.id,
            relationship=UnitRelationship.OWNER,
        )
    )
    db.commit()
    [error] = _report(
        db, world, sender, publisher, {**leak, "title": "Outro vazamento"}, message="vazou de novo"
    )
    assert "Ask which unit" in error and "Bloco A 101" in error and "Bloco A 202" in error


def test_location_is_required_outside_the_unit(db, world, sender, publisher, maria):
    [error] = _report(db, world, sender, publisher, {**GATE, "location": None})
    assert "location" in error
    assert db.scalar(select(func.count()).select_from(MaintenanceTicket)) == 0


def test_same_message_never_creates_two_tickets(db, world, maria, publisher):
    kwargs = dict(
        condominium=world.condo_a,
        resident=maria,
        conversation=None,
        unit_id=None,
        title="Portão",
        description="Não abre",
        location="Garagem",
        ai_category=TicketCategory.GATES_ACCESS,
        ai_priority=TicketPriority.NORMAL,
        idempotency_key="msg:abc:ticket:portao",
        agent_run_id=None,
    )
    first, created = tickets.create_for_resident(db, publisher, **kwargs)
    again, created_again = tickets.create_for_resident(db, publisher, **kwargs)
    assert created and not created_again and first.id == again.id


def test_emergency_alerts_on_call_and_hands_over(db, world, sender, publisher, maria):
    db.add_all(
        [
            EmergencyContact(
                condominium_id=world.condo_a.id, name="Zelador", phone_e164="+5511933330001"
            ),
            EmergencyContact(
                condominium_id=world.condo_a.id, name="Síndico", phone_e164="+5511933330002"
            ),
        ]
    )
    db.commit()
    gas = {
        **GATE,
        "title": "Cheiro de gás no 3º andar",
        "description": "Cheiro forte de gás no corredor",
        "location": "Corredor do 3º andar",
        "category": "security",
        "priority": "high",
    }
    [result] = _report(db, world, sender, publisher, gas, message="cheiro de gás!")

    assert result["emergency_procedure_started"] is True
    assert db.scalar(select(Conversation.status)) == ConversationStatus.ESCALATED
    jobs = publisher.take(notifications.NOTIFICATION_TOPIC)
    assert len(jobs) == 2
    for job in jobs:
        notifications.deliver(db, uuid.UUID(job["notification_id"]), sender)
    # On-call numbers never wrote to us, so the alert must be a template.
    assert {t[1] for t in sender.templates} == {"+5511933330001", "+5511933330002"}
    assert all(t[2] == "zela_emergency_alert" for t in sender.templates)
    assert "Cheiro de gás no 3º andar" in sender.templates[0][3]


def test_emergency_without_on_call_contacts_is_recorded(db, world, sender, publisher, maria):
    gas = {
        **GATE,
        "title": "Incêndio na lixeira",
        "description": "Fogo na lixeira",
        "category": "security",
        "priority": "emergency",
    }
    _report(db, world, sender, publisher, gas)
    notes = db.scalars(
        select(TicketEvent.note).where(TicketEvent.event_type == "emergency_alerted")
    ).all()
    assert notes == ["Nenhum contato de plantão configurado: ninguém foi alertado por WhatsApp."]


def test_resident_sees_only_own_tickets(db, world, sender, publisher, maria):
    _report(db, world, sender, publisher, GATE)
    make_resident(db, world.condo_a, phone="+5511922223333", name="João Vizinho")
    llm = ScriptedLLM([call("get_my_tickets"), call("get_my_tickets", number=1), say("ok")])
    deliver(db, world.condo_a, "meus chamados?", sender=sender, llm=llm, from_e164="+5511922223333")
    listed, by_number = llm.sessions[0].outcomes
    assert json.loads(listed.content) == {"tickets": []}
    assert by_number.is_error and "#1" in by_number.content


# --- Staff workflow --------------------------------------------------------------------------


@pytest.fixture
def ticket(db, world, sender, publisher, maria):
    _report(db, world, sender, publisher, GATE)
    publisher.jobs.clear()
    return db.scalar(select(MaintenanceTicket))


def _url(world, ticket, suffix=""):
    return f"/v1/condominiums/{world.condo_a.id}/tickets/{ticket.id}{suffix}"


def test_list_and_detail(client, world, ticket):
    items = client.get(
        f"/v1/condominiums/{world.condo_a.id}/tickets", params={"open": True}, headers=MANAGER
    ).json()["items"]
    assert [(i["number"], i["reporter_name"], i["location"]) for i in items] == [
        (1, "Maria Silva", "Garagem, portão de saída")
    ]
    detail = client.get(_url(world, ticket), headers=MANAGER).json()
    assert detail["allowed_transitions"] == [
        "in_progress",
        "waiting_information",
        "waiting_external",
        "resolved",
        "closed",
    ]
    assert detail["ai_suggested_category"] == "gates_access"


def test_status_change_notifies_resident_with_stored_state(
    client, db, world, sender, publisher, ticket
):
    response = client.post(
        _url(world, ticket, "/status"),
        json={"status": "in_progress", "note": "Técnico chega às 14h."},
        headers=MANAGER,
    )
    assert response.status_code == 200
    [job] = publisher.take(notifications.NOTIFICATION_TOPIC)
    notifications.deliver(db, uuid.UUID(job["notification_id"]), sender)

    # The resident wrote recently, so it goes as a plain message in the same conversation.
    message = outbound(db)[-1]
    assert message.kind == MessageKind.NOTIFICATION
    assert message.body == (
        "Atualização do seu chamado #1 (Portão da garagem não abre): a equipe começou a cuidar "
        "do problema. Mensagem da equipe: Técnico chega às 14h."
    )
    assert sender.sent[-1][1] == RESIDENT_PHONE


def test_outdated_status_notification_is_skipped(client, db, world, sender, publisher, ticket):
    client.post(_url(world, ticket, "/status"), json={"status": "in_progress"}, headers=MANAGER)
    client.post(_url(world, ticket, "/status"), json={"status": "resolved"}, headers=MANAGER)
    first, second = publisher.take(notifications.NOTIFICATION_TOPIC)
    notifications.deliver(db, uuid.UUID(first["notification_id"]), sender)
    notifications.deliver(db, uuid.UUID(second["notification_id"]), sender)
    statuses = db.scalars(
        select(NotificationEvent.status).order_by(NotificationEvent.created_at)
    ).all()
    assert statuses == [DeliveryStatus.SKIPPED, DeliveryStatus.SENT]
    assert "resolvido" in outbound(db)[-1].body


def test_outside_24h_window_uses_template(client, db, world, sender, publisher, ticket):
    conversation = db.scalar(select(Conversation))
    conversation.last_inbound_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    client.post(_url(world, ticket, "/status"), json={"status": "resolved"}, headers=MANAGER)
    [job] = publisher.take(notifications.NOTIFICATION_TOPIC)
    notifications.deliver(db, uuid.UUID(job["notification_id"]), sender)
    [(_, to, name, params)] = sender.templates
    assert (to, name) == (RESIDENT_PHONE, "zela_ticket_update")
    assert params[0] == "1" and "resolvido" in params[2]


def test_invalid_and_final_transitions(client, world, ticket):
    assert (
        client.post(
            _url(world, ticket, "/status"), json={"status": "closed"}, headers=MANAGER
        ).status_code
        == 200
    )
    assert (
        client.post(
            _url(world, ticket, "/status"), json={"status": "in_progress"}, headers=MANAGER
        ).status_code
        == 409
    )


def test_internal_notes_stay_internal(client, db, world, publisher, ticket):
    client.post(
        _url(world, ticket, "/notes"),
        json={"body": "Ligar para a Elevadores SA", "public": False},
        headers=MANAGER,
    )
    assert publisher.take(notifications.NOTIFICATION_TOPIC) == []
    client.post(
        _url(world, ticket, "/notes"),
        json={"body": "Peça encomendada", "public": True},
        headers=MANAGER,
    )
    assert len(publisher.take(notifications.NOTIFICATION_TOPIC)) == 1


def test_assign_only_to_condominium_staff(client, world, ticket):
    ok = client.put(
        _url(world, ticket, "/assignee"), json={"user_id": str(world.staff_a.id)}, headers=MANAGER
    )
    assert ok.json()["assignee_email"] == "staff.a@example.com"
    outsider = client.put(
        _url(world, ticket, "/assignee"), json={"user_id": str(world.manager_b.id)}, headers=MANAGER
    )
    assert outsider.status_code == 422


def test_reclassify_keeps_ai_suggestion(client, world, ticket):
    body = client.put(
        _url(world, ticket, "/classification"), json={"priority": "normal"}, headers=MANAGER
    ).json()
    assert body["priority"] == "normal" and body["ai_suggested_priority"] == "high"
    assert body["events"][-1]["event_type"] == "reclassified"


def test_front_desk_reads_but_cannot_change(client, world, ticket):
    staff = auth("staff.a@example.com")
    assert client.get(_url(world, ticket), headers=staff).status_code == 200
    assert (
        client.post(
            _url(world, ticket, "/status"), json={"status": "in_progress"}, headers=staff
        ).status_code
        == 403
    )


def test_other_condominium_cannot_touch_ticket(client, world, ticket):
    url = f"/v1/condominiums/{world.condo_b.id}/tickets/{ticket.id}"
    assert client.get(url, headers=auth("manager.b@example.com")).status_code == 404
