"""People over WhatsApp for sheet-backed condominiums (ADR 0011): the manager's number,
identifying senders from the Pessoas sheet, and registering people in two steps."""

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agents import zela
from app.agents.tools import ToolContext, was_previewed
from app.core import crypto
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import ScriptedLLM, call, say
from app.models import AgentRun, AuditEvent, Conversation, DriveConnection, NotificationEvent
from app.models.enums import AgentRunStatus, ConversationStatus, DeliveryStatus
from app.services import manager_phone, notifications
from app.workers import inbound
from tests.factories import FakePublisher, auth
from tests.sheets import MANAGER_PHONE, add_row, confirm_manager, connect_drive, row_dict, tab
from tests.whatsapp import deliver, outbound

OWNER = "owner1@example.com"
ANA = "+5511987654321"


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def jobs():
    return FakePublisher()


@pytest.fixture
def condo(client, db, world, google, publisher):
    connect_drive(client, db, google, world.condo_a, OWNER)
    return world.condo_a


@pytest.fixture
def people_tab(db, google, condo):
    return tab(db, google, condo)


def _last_reply(db) -> str:
    return outbound(db)[-1].body


def _say_last_outcome(session):
    return say("resultado: " + session.outcomes[-1].content)


# Manager's number


def test_owner_sets_the_manager_number_and_a_confirmation_is_queued(client, db, world, publisher):
    response = client.put(
        f"/v1/condominiums/{world.condo_a.id}/manager-phone",
        json={"number": "(11) 95555-0000"},
        headers=auth(OWNER),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manager_phone_e164"] == MANAGER_PHONE
    assert body["manager_phone_confirmed_at"] is None
    notification = db.scalar(select(NotificationEvent))
    assert notification.template == "zela_manager_confirmation"
    assert notification.recipient_e164 == MANAGER_PHONE
    assert publisher.take(notifications.NOTIFICATION_TOPIC)
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "condominium.manager_phone_set")
    )
    assert event.data == {}  # never the number itself


def test_manager_number_rules(client, world):
    url = f"/v1/condominiums/{world.condo_a.id}/manager-phone"
    assert client.put(url, json={"number": "123"}, headers=auth(OWNER)).status_code == 422
    staff_manager = client.put(
        url, json={"number": MANAGER_PHONE}, headers=auth("manager.a@example.com")
    )
    assert staff_manager.status_code == 403
    # condo_c has no WhatsApp number yet: nothing to send the confirmation from.
    no_whatsapp = client.put(
        f"/v1/condominiums/{world.condo_c.id}/manager-phone",
        json={"number": MANAGER_PHONE},
        headers=auth("owner2@example.com"),
    )
    assert no_whatsapp.status_code == 409


def test_replying_sim_from_that_number_confirms_it(client, db, world, sender, publisher):
    client.put(
        f"/v1/condominiums/{world.condo_a.id}/manager-phone",
        json={"number": MANAGER_PHONE},
        headers=auth(OWNER),
    )
    deliver(db, world.condo_a, "oi?", sender=sender, from_e164=MANAGER_PHONE)
    assert "responda SIM" in _last_reply(db)
    assert world.condo_a.manager_phone_confirmed_at is None

    deliver(db, world.condo_a, "Sim!", sender=sender, from_e164=MANAGER_PHONE)
    db.refresh(world.condo_a)
    assert world.condo_a.manager_phone_confirmed_at is not None
    assert _last_reply(db).startswith("Pronto! Este é agora o WhatsApp do síndico")
    assert "conecte o Google Drive" in _last_reply(db)  # condo_a has no Drive yet


def test_sim_from_another_number_or_after_expiry_does_not_confirm(client, db, world, sender):
    client.put(
        f"/v1/condominiums/{world.condo_a.id}/manager-phone",
        json={"number": MANAGER_PHONE},
        headers=auth(OWNER),
    )
    deliver(db, world.condo_a, "sim", sender=sender, from_e164="+5511944443333")
    assert world.condo_a.manager_phone_confirmed_at is None

    world.condo_a.manager_phone_requested_at -= manager_phone.CONFIRMATION_TTL + timedelta(hours=1)
    db.commit()
    deliver(db, world.condo_a, "sim", sender=sender, from_e164=MANAGER_PHONE)
    db.refresh(world.condo_a)
    assert world.condo_a.manager_phone_confirmed_at is None
    assert _last_reply(db) == manager_phone.EXPIRED


def test_confirmation_for_a_replaced_number_is_not_sent(client, db, world, sender):
    url = f"/v1/condominiums/{world.condo_a.id}/manager-phone"
    client.put(url, json={"number": MANAGER_PHONE}, headers=auth(OWNER))
    first = db.scalar(select(NotificationEvent))
    client.put(url, json={"number": "+5511944443333"}, headers=auth(OWNER))

    notifications.deliver(db, first.id, sender)
    db.refresh(first)
    assert first.status == DeliveryStatus.SKIPPED
    assert sender.sent == [] and sender.templates == []


# Identifying senders


def test_unknown_numbers_get_a_fixed_reply_without_the_model(db, condo, sender, google):
    llm = ScriptedLLM([])
    deliver(db, condo, "Bom dia", sender=sender, llm=llm, google=google)
    assert _last_reply(db) == inbound.UNKNOWN_PERSON.format(condo=condo.name)
    assert llm.sessions == []


def test_a_resident_row_identifies_the_sender_with_their_own_tools(
    db, condo, people_tab, sender, google
):
    add_row(people_tab, name="Ana Souza", whatsapp="(11) 98765-4321", unit="302", role="Moradora")
    llm = ScriptedLLM([call("get_my_registration"), _say_last_outcome])
    deliver(db, condo, "qual meu cadastro?", sender=sender, llm=llm, google=google)

    session = llm.sessions[0]
    assert session.system == zela.SYSTEM_PROMPT
    assert [t.name for t in session.tools] == [
        "get_my_registration",
        "report_occurrence",
        "get_my_occurrences",
    ]
    assert "Papel: Morador" in session.context and "Ana" in session.context
    data = json.loads(session.outcomes[0].content)
    assert data == {
        "name": "Ana Souza",
        "role": "Morador",
        "units": [{"place": "302", "role": "Morador"}],
    }


@pytest.mark.parametrize(
    "row",
    [
        {"status": "Inativo", "role": "Morador"},
        {"role": "Vizinho"},  # not a role Zela knows
        {"role": "Morador", "whatsapp": "não tem"},
    ],
)
def test_rows_that_grant_nothing(db, condo, people_tab, sender, google, row):
    add_row(people_tab, **{"name": "Ana", "whatsapp": ANA, "unit": "302", **row})
    llm = ScriptedLLM([])
    deliver(db, condo, "oi", sender=sender, llm=llm, google=google)
    assert llm.sessions == []
    assert "Não encontrei este número" in _last_reply(db)


def test_the_broadest_role_applies_and_the_manager_needs_a_confirmed_number(
    db, condo, people_tab, sender, google
):
    add_row(people_tab, name="Ana", whatsapp=ANA, unit="302", role="Morador")
    add_row(people_tab, name="Ana", whatsapp=ANA, unit="101", role="Proprietária")
    llm = ScriptedLLM([say("oi")])
    deliver(db, condo, "oi", sender=sender, llm=llm, google=google)
    assert "Papel: Proprietário" in llm.sessions[0].context
    assert "302 (Morador), 101 (Proprietário)" in llm.sessions[0].context

    # The confirmed number is the manager even with no row in Pessoas.
    confirm_manager(db, condo)
    llm = ScriptedLLM([say("oi")])
    deliver(db, condo, "oi", sender=sender, llm=llm, google=google, from_e164=MANAGER_PHONE)
    assert "Papel: Síndico" in llm.sessions[0].context
    assert [t.name for t in llm.sessions[0].tools] == [
        "get_my_registration",
        "report_occurrence",
        "get_my_occurrences",
        "register_person",
        "find_people",
        "update_person",
        "find_occurrences",
        "update_occurrence",
    ]


def test_an_unreadable_sheet_is_explained_to_the_manager_only(
    db, condo, people_tab, sender, google
):
    add_row(people_tab, name="Ana", whatsapp=ANA, unit="302", role="Morador")
    confirm_manager(db, condo)
    connection = db.scalar(select(DriveConnection))
    google.revoked.add(crypto.decrypt_secret(connection.refresh_token_encrypted))

    deliver(db, condo, "oi", sender=sender, google=google, from_e164=MANAGER_PHONE)
    assert "Não consigo acessar as planilhas" in _last_reply(db)
    deliver(db, condo, "oi", sender=sender, google=google)
    assert _last_reply(db) == inbound.SHEETS_UNAVAILABLE


def test_an_escalated_conversation_does_not_silence_the_sheet_agent(
    db, condo, people_tab, sender, google
):
    add_row(people_tab, name="Ana", whatsapp=ANA, unit="302", role="Morador")
    deliver(db, condo, "oi", sender=sender, google=google, llm=ScriptedLLM([say("Olá!")]))
    conversation = db.scalar(select(Conversation))
    conversation.status = ConversationStatus.ESCALATED
    db.commit()
    deliver(
        db, condo, "oi de novo", sender=sender, google=google, llm=ScriptedLLM([say("Oi, Ana")])
    )
    assert _last_reply(db) == "Oi, Ana"


# Registering people (manager)

MARIA = {
    "name": "Maria  Oliveira",
    "whatsapp": "11 91234-5678",
    "role": "morador",
    "block": "B",
    "unit": "204",
}


def _as_manager(db, condo, text, script, sender, google, jobs=None):
    llm = ScriptedLLM(script)
    deliver(
        db,
        condo,
        text,
        sender=sender,
        llm=llm,
        google=google,
        from_e164=MANAGER_PHONE,
        publisher=jobs,
    )
    return llm.sessions[0]


def test_registration_takes_a_summary_then_a_later_confirmation(
    db, condo, people_tab, sender, google, jobs
):
    confirm_manager(db, condo)
    session = _as_manager(
        db,
        condo,
        "cadastra a Maria",
        [call("register_person", **MARIA), _say_last_outcome],
        sender,
        google,
    )
    preview = json.loads(session.outcomes[0].content)
    assert preview["needs_confirmation"] is True
    assert preview["summary"]["whatsapp"] == "+5511912345678"
    assert preview["summary"]["name"] == "Maria Oliveira"
    assert len(people_tab.rows) == 1  # nothing written yet

    session = _as_manager(
        db,
        condo,
        "sim, pode cadastrar",
        [call("register_person", **MARIA, confirmed=True), _say_last_outcome],
        sender,
        google,
        jobs,
    )
    result = json.loads(session.outcomes[0].content)
    assert result["registered"] is True and result["row"] == 2
    row = row_dict(people_tab, 2)
    assert row["zela_id"] == result["id"] and row["zela_id"].startswith("P-")
    assert (row["name"], row["whatsapp"], row["block"], row["unit"]) == (
        "Maria Oliveira",
        "+5511912345678",
        "B",
        "204",
    )
    assert (row["role"], row["status"]) == ("Morador", "Ativo")
    assert row["created_at"]

    welcome = db.scalar(
        select(NotificationEvent).where(NotificationEvent.template == "zela_person_welcome")
    )
    assert welcome.recipient_e164 == "+5511912345678"
    assert jobs.take(notifications.NOTIFICATION_TOPIC)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "person.registered"))
    assert event.data == {"register": "people", "zela_id": result["id"], "role": "resident"}

    # Maria can now use Zela.
    llm = ScriptedLLM([say("Olá, Maria")])
    deliver(db, condo, "oi", sender=sender, llm=llm, google=google, from_e164="+5511912345678")
    assert "Papel: Morador" in llm.sessions[0].context


def test_one_message_cannot_both_request_and_confirm(db, condo, people_tab, sender, google):
    confirm_manager(db, condo)
    session = _as_manager(
        db,
        condo,
        "cadastra a Maria, já confirmo",
        [
            call("register_person", **MARIA),
            call("register_person", **MARIA, confirmed=True),
            _say_last_outcome,
        ],
        sender,
        google,
    )
    assert session.outcomes[1].is_error and "confirmed=false" in session.outcomes[1].content
    assert len(people_tab.rows) == 1


def test_confirming_different_details_than_the_summary_is_refused(
    db, condo, people_tab, sender, google
):
    confirm_manager(db, condo)
    _as_manager(
        db, condo, "cadastra", [call("register_person", **MARIA), say("Confere?")], sender, google
    )
    session = _as_manager(
        db,
        condo,
        "sim",
        [call("register_person", **{**MARIA, "unit": "999"}, confirmed=True), _say_last_outcome],
        sender,
        google,
    )
    assert session.outcomes[0].is_error
    assert len(people_tab.rows) == 1


def test_a_retried_confirmation_writes_one_row(db, condo, people_tab, sender, google):
    confirm_manager(db, condo)
    _as_manager(
        db, condo, "cadastra", [call("register_person", **MARIA), say("Confere?")], sender, google
    )
    _as_manager(
        db,
        condo,
        "sim",
        [
            call("register_person", **MARIA, confirmed=True),
            call("register_person", **MARIA, confirmed=True),
            _say_last_outcome,
        ],
        sender,
        google,
    )
    assert len(people_tab.rows) == 2
    assert db.scalar(
        select(NotificationEvent).where(NotificationEvent.template == "zela_person_welcome")
    )


def test_registration_validates_its_inputs(db, condo, people_tab, sender, google):
    confirm_manager(db, condo)
    add_row(
        people_tab,
        zela_id="P-1",
        name="Maria",
        whatsapp="11912345678",
        block="B",
        unit="204",
        role="Morador",
    )
    session = _as_manager(
        db,
        condo,
        "cadastra",
        [
            call("register_person", **{**MARIA, "whatsapp": "00000000"}),
            call("register_person", **{**MARIA, "unit": ""}),
            call("register_person", **MARIA),  # already there
            call("register_person", **{**MARIA, "role": "funcionario", "unit": "", "block": ""}),
            say("ok"),
        ],
        sender,
        google,
    )
    bad_phone, no_unit, duplicate, staff = session.outcomes
    assert bad_phone.is_error and "not valid" in bad_phone.content
    assert no_unit.is_error and "unit" in no_unit.content
    assert json.loads(duplicate.content)["already_registered"] is True
    staff_summary = json.loads(staff.content)["summary"]
    assert staff_summary["role"] == "Funcionário" and staff_summary["also_registered_in"] == ["204"]


def test_residents_cannot_register_people(db, condo, people_tab, sender, google):
    add_row(people_tab, name="Ana", whatsapp=ANA, unit="302", role="Morador")
    llm = ScriptedLLM([call("register_person", **MARIA), _say_last_outcome])
    deliver(db, condo, "cadastra a Maria", sender=sender, llm=llm, google=google)
    assert llm.sessions[0].outcomes[0].is_error
    assert "Unknown tool" in llm.sessions[0].outcomes[0].content
    assert len(people_tab.rows) == 2


def test_find_and_deactivate_a_hand_added_person(db, condo, people_tab, sender, google):
    confirm_manager(db, condo)
    add_row(people_tab, name="Carlos Lima", whatsapp="11 93333-2222", unit="501", role="Morador")
    session = _as_manager(
        db,
        condo,
        "buscar Carlos",
        [call("find_people", query="carlos"), _say_last_outcome],
        sender,
        google,
    )
    [carlos] = json.loads(session.outcomes[0].content)["people"]
    assert carlos["id"].startswith("P-") and row_dict(people_tab, 2)["zela_id"] == carlos["id"]

    args = {"person_id": carlos["id"], "status": "inativo"}
    _as_manager(
        db, condo, "desativa ele", [call("update_person", **args), say("Confere?")], sender, google
    )
    assert row_dict(people_tab, 2)["status"] == ""
    session = _as_manager(
        db,
        condo,
        "sim",
        [call("update_person", **args, confirmed=True), _say_last_outcome],
        sender,
        google,
    )
    assert json.loads(session.outcomes[0].content)["updated"] is True
    assert row_dict(people_tab, 2)["status"] == "Inativo"
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "person.updated")).data == {
        "register": "people",
        "zela_id": carlos["id"],
        "fields": ["status"],
    }

    deliver(
        db,
        condo,
        "oi",
        sender=sender,
        google=google,
        from_e164="+5511933332222",
        llm=ScriptedLLM([]),
    )
    assert "Não encontrei este número" in _last_reply(db)


def test_previews_expire(db, condo, people_tab, sender, google):
    confirm_manager(db, condo)
    _as_manager(
        db, condo, "cadastra", [call("register_person", **MARIA), say("Confere?")], sender, google
    )
    for run in db.scalars(select(AgentRun)):
        run.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    session = _as_manager(
        db,
        condo,
        "sim",
        [call("register_person", **MARIA, confirmed=True), _say_last_outcome],
        sender,
        google,
    )
    assert session.outcomes[0].is_error
    assert len(people_tab.rows) == 1


def test_a_preview_in_the_current_run_does_not_count(db, condo):
    """Backstop: a run's own summary never authorizes its confirmation."""
    conversation = Conversation(condominium_id=condo.id, contact_e164=MANAGER_PHONE)
    db.add(conversation)
    db.flush()
    run = AgentRun(
        condominium_id=condo.id,
        conversation_id=conversation.id,
        agent="zela",
        status=AgentRunStatus.RUNNING,
        tool_calls=[{"tool": "register_person", "ok": True, "preview_key": "k"}],
    )
    db.add(run)
    db.flush()
    ctx = ToolContext(
        condominium_id=condo.id,
        conversation_id=conversation.id,
        agent_run_id=run.id,
        idempotency_key="msg:x",
        publisher=FakePublisher(),
    )
    assert not was_previewed(db, ctx, "register_person", "k")
    assert was_previewed(db, replace(ctx, agent_run_id=uuid.uuid4()), "register_person", "k")
