"""Occurrences over WhatsApp in the Ocorrências sheet (ADR 0012)."""

import json

import pytest
from sqlalchemy import select

from app.core import crypto
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import ScriptedLLM, call, say
from app.models import AuditEvent, DriveConnection, EmergencyContact, NotificationEvent
from app.models.enums import DeliveryStatus, RegisterKind
from app.services import drive, notifications
from app.workers import inbound
from tests.factories import FakePublisher
from tests.sheets import MANAGER_PHONE, add_row, confirm_manager, connect_drive, row_dict, tab
from tests.whatsapp import deliver, outbound

OWNER = "owner1@example.com"
ANA = "+5511987654321"
BRUNO = "+5511976543210"
ON_CALL = "+5511933330001"
OCC = RegisterKind.OCCURRENCES

GATE = {
    "type": "manutencao",
    "description": "O portão da garagem não abre desde ontem",
    "location": "Garagem, portão 2",
    "in_own_unit": False,
    "category": "gates_access",
    "priority": "normal",
}


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def jobs():
    return FakePublisher()


@pytest.fixture
def condo(client, db, world, google, publisher):
    connect_drive(client, db, google, world.condo_a, OWNER)
    people = tab(db, google, world.condo_a)
    add_row(people, zela_id="P-ANA", name="Ana Souza", whatsapp=ANA, unit="302", role="Morador")
    add_row(
        people,
        zela_id="P-B1",
        name="Bruno Reis",
        whatsapp=BRUNO,
        block="A",
        unit="101",
        role="Proprietário",
    )
    add_row(
        people,
        zela_id="P-B2",
        name="Bruno Reis",
        whatsapp=BRUNO,
        block="B",
        unit="202",
        role="Proprietário",
    )
    db.add(EmergencyContact(condominium_id=world.condo_a.id, name="Seu Jorge", phone_e164=ON_CALL))
    db.commit()
    confirm_manager(db, world.condo_a)
    return world.condo_a


@pytest.fixture
def sheet(db, google, condo):
    return tab(db, google, condo, OCC)


def _say_last(session):
    return say("resultado: " + session.outcomes[-1].content)


def _run(db, condo, google, script, *, text="mensagem", phone=ANA, sender=None, jobs=None):
    llm = ScriptedLLM(script)
    deliver(
        db,
        condo,
        text,
        sender=sender or RecordingSender(),
        llm=llm,
        google=google,
        from_e164=phone,
        publisher=jobs,
    )
    return llm.sessions[0]


def _outcome(session, index=0):
    return json.loads(session.outcomes[index].content)


def test_a_report_becomes_a_numbered_row(db, condo, sheet, google):
    session = _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    assert _outcome(session) == {
        "reference": "#1",
        "category": "Portões e acesso",
        "priority": "Normal",
        "emergency_procedure_started": False,
        "on_call_alerted": 0,
    }
    row = row_dict(sheet, 2, OCC)
    assert row["zela_id"].startswith("O-") and row["number"] == "1"
    assert (row["type"], row["status"], row["location"]) == (
        "Manutenção",
        "Aberta",
        "Garagem, portão 2",
    )
    assert (row["category"], row["priority"]) == ("Portões e acesso", "Normal")
    assert row["ai_suggestion"] == "Categoria: Portões e acesso · Prioridade: Normal"
    assert (row["reported_by"], row["reported_by_id"]) == ("Ana Souza", "P-ANA")
    assert row["unit"] == "" and row["opened_at"]

    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "occurrence.reported"))
    assert event.data["number"] == "1" and "description" not in json.dumps(event.data)

    second = _run(
        db,
        condo,
        google,
        [
            call("report_occurrence", **{**GATE, "description": "Lâmpada queimada no hall"}),
            _say_last,
        ],
    )
    assert _outcome(second)["reference"] == "#2"


def test_own_unit_comes_from_the_senders_rows(db, condo, sheet, google):
    _run(db, condo, google, [call("report_occurrence", **{**GATE, "in_own_unit": True}), _say_last])
    assert row_dict(sheet, 2, OCC)["unit"] == "302"

    ambiguous = _run(
        db,
        condo,
        google,
        [call("report_occurrence", **{**GATE, "in_own_unit": True}), _say_last],
        phone=BRUNO,
    )
    assert ambiguous.outcomes[0].is_error and "A 101, B 202" in ambiguous.outcomes[0].content
    not_theirs = _run(
        db,
        condo,
        google,
        [call("report_occurrence", **{**GATE, "unit": "302"}), _say_last],
        phone=BRUNO,
    )
    assert not_theirs.outcomes[0].is_error

    _run(
        db,
        condo,
        google,
        [call("report_occurrence", **{**GATE, "in_own_unit": True, "unit": "202"}), _say_last],
        phone=BRUNO,
    )
    row = row_dict(sheet, 3, OCC)
    assert (row["block"], row["unit"], row["reported_by_id"]) == ("B", "202", "P-B2")


def test_a_retried_report_writes_one_row(db, condo, sheet, google):
    session = _run(
        db,
        condo,
        google,
        [call("report_occurrence", **GATE), call("report_occurrence", **GATE), _say_last],
    )
    assert _outcome(session, 0)["reference"] == _outcome(session, 1)["reference"] == "#1"
    assert len(sheet.rows) == 2


def test_emergencies_alert_on_call_and_the_manager(db, condo, sheet, google, jobs):
    gas = {
        **GATE,
        "description": "Cheiro forte de gás no corredor",
        "location": "3º andar",
        "category": "other",
    }
    session = _run(db, condo, google, [call("report_occurrence", **gas), _say_last], jobs=jobs)
    result = _outcome(session)
    assert result["priority"] == "Emergência"  # by keyword, though the model said normal
    assert result["emergency_procedure_started"] is True and result["on_call_alerted"] == 2
    alerts = db.scalars(
        select(NotificationEvent).where(NotificationEvent.template == "zela_occurrence_emergency")
    ).all()
    assert {a.recipient_e164 for a in alerts} == {ON_CALL, MANAGER_PHONE}
    params = alerts[0].data["params"]
    assert params["number"] == "1" and params["reporter"] == "Ana"
    assert params["location"] == "3º andar"
    assert len(jobs.take(notifications.NOTIFICATION_TOPIC)) == 2
    assert row_dict(sheet, 2, OCC)["ai_suggestion"] == "Categoria: Outros · Prioridade: Normal"


def test_the_reporter_is_not_alerted_about_their_own_emergency(db, condo, sheet, google):
    fire = {**GATE, "description": "Fumaça saindo do quadro de luz", "category": "electrical"}
    _run(db, condo, google, [call("report_occurrence", **fire), _say_last], phone=MANAGER_PHONE)
    recipients = {
        n.recipient_e164
        for n in db.scalars(
            select(NotificationEvent).where(
                NotificationEvent.template == "zela_occurrence_emergency"
            )
        )
    }
    assert recipients == {ON_CALL}


def test_people_see_only_their_own_occurrences(db, condo, sheet, google):
    _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    _run(
        db,
        condo,
        google,
        [call("report_occurrence", **{**GATE, "description": "Barulho de obra às 22h"}), _say_last],
        phone=BRUNO,
    )

    mine = _run(db, condo, google, [call("get_my_occurrences"), _say_last])
    assert [o["number"] for o in _outcome(mine)["occurrences"]] == ["1"]
    assert "reported_by" not in _outcome(mine)["occurrences"][0]

    listing = _run(db, condo, google, [call("find_occurrences"), _say_last])
    assert listing.outcomes[0].is_error and "Unknown tool" in listing.outcomes[0].content

    manager = _run(
        db,
        condo,
        google,
        [call("find_occurrences", query="barulho"), _say_last],
        phone=MANAGER_PHONE,
    )
    [found] = _outcome(manager)["occurrences"]
    assert found["number"] == "2" and found["reported_by"] == "Bruno Reis"


def test_manager_resolves_in_two_steps_and_the_reporter_is_told(db, condo, sheet, google, jobs):
    _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    args = {
        "number": 1,
        "status": "resolvida",
        "note_for_reporter": "O técnico trocou o motor.",
        "internal_note": "Custo R$ 450",
    }
    preview = _run(
        db, condo, google, [call("update_occurrence", **args), _say_last], phone=MANAGER_PHONE
    )
    assert _outcome(preview)["reporter_will_be_notified"] is True
    assert row_dict(sheet, 2, OCC)["status"] == "Aberta"

    done = _run(
        db,
        condo,
        google,
        [call("update_occurrence", **args, confirmed=True), _say_last],
        phone=MANAGER_PHONE,
        jobs=jobs,
    )
    assert _outcome(done)["reporter_notified"] is True
    row = row_dict(sheet, 2, OCC)
    assert row["status"] == "Resolvida" and row["closed_at"]
    assert row["notes"].endswith("Custo R$ 450")

    [update] = db.scalars(
        select(NotificationEvent).where(NotificationEvent.template == "zela_occurrence_update")
    ).all()
    assert update.recipient_e164 == ANA
    assert update.data["params"]["update"].endswith("O técnico trocou o motor.")
    assert "Custo" not in json.dumps(update.data)
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "occurrence.updated")).data[
        "fields"
    ] == [
        "closed_at",
        "notes",
        "status",
    ]


def test_an_update_is_not_sent_if_the_sheet_changed_first(db, condo, sheet, google):
    _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    args = {"number": 1, "status": "em_andamento"}
    _run(db, condo, google, [call("update_occurrence", **args), _say_last], phone=MANAGER_PHONE)
    _run(
        db,
        condo,
        google,
        [call("update_occurrence", **args, confirmed=True), _say_last],
        phone=MANAGER_PHONE,
    )
    update = db.scalar(
        select(NotificationEvent).where(NotificationEvent.template == "zela_occurrence_update")
    )

    # The manager resolves it by hand in the sheet before the notification goes out.
    status_col = sheet.rows[0].index("Status")
    sheet.rows[1][status_col] = "Resolvida"
    sender = RecordingSender()
    notifications.deliver(db, update.id, sender, google)
    db.refresh(update)
    assert update.status == DeliveryStatus.SKIPPED and sender.sent == []


def test_an_update_waits_when_the_sheet_cannot_be_read(db, condo, sheet, google):
    _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    args = {"number": 1, "status": "em_andamento"}
    _run(db, condo, google, [call("update_occurrence", **args), _say_last], phone=MANAGER_PHONE)
    _run(
        db,
        condo,
        google,
        [call("update_occurrence", **args, confirmed=True), _say_last],
        phone=MANAGER_PHONE,
    )
    update = db.scalar(
        select(NotificationEvent).where(NotificationEvent.template == "zela_occurrence_update")
    )
    connection = db.scalar(select(DriveConnection))
    google.revoked.add(crypto.decrypt_secret(connection.refresh_token_encrypted))

    with pytest.raises(drive.RegisterUnavailable):
        notifications.deliver(db, update.id, RecordingSender(), google)
    db.rollback()
    db.refresh(update)
    assert update.status == DeliveryStatus.PENDING  # the sweeper retries it


def test_updating_a_hand_typed_occurrence(db, condo, sheet, google):
    add_row(sheet, OCC, number="7", description="Infiltração no teto da garagem", status="Aberta")
    args = {"number": 7, "assignee": "Zelador"}
    _run(db, condo, google, [call("update_occurrence", **args), _say_last], phone=MANAGER_PHONE)
    done = _run(
        db,
        condo,
        google,
        [call("update_occurrence", **args, confirmed=True), _say_last],
        phone=MANAGER_PHONE,
    )
    assert _outcome(done)["reporter_notified"] is False  # no status change, no reporter
    row = row_dict(sheet, 2, OCC)
    assert row["assignee"] == "Zelador" and row["zela_id"] == "O-ROW2"

    missing = _run(
        db,
        condo,
        google,
        [call("update_occurrence", number=99, status="resolvida"), _say_last],
        phone=MANAGER_PHONE,
    )
    assert missing.outcomes[0].is_error and "#99" in missing.outcomes[0].content


def test_on_call_numbers_outside_pessoas_get_an_acknowledgement(db, condo, google):
    deliver(
        db,
        condo,
        "ok, estou indo",
        sender=RecordingSender(),
        google=google,
        from_e164=ON_CALL,
        llm=ScriptedLLM([]),
    )
    assert outbound(db)[-1].body == inbound.ON_CALL_ACK_SHEETS.format(condo=condo.name)


def test_an_update_without_a_summary_first_is_refused(db, condo, sheet, google):
    _run(db, condo, google, [call("report_occurrence", **GATE), _say_last])
    blind = _run(
        db,
        condo,
        google,
        [call("update_occurrence", number=1, status="cancelada", confirmed=True), _say_last],
        phone=MANAGER_PHONE,
    )
    assert blind.outcomes[0].is_error and "confirmed=false" in blind.outcomes[0].content
    assert row_dict(sheet, 2, OCC)["status"] == "Aberta"
