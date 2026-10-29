"""Deliveries over WhatsApp in the Encomendas sheet (ADR 0013)."""

import json

import pytest
from sqlalchemy import select

from app.agents import zela
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import RuleBasedLLM, ScriptedLLM, call, say
from app.models import AuditEvent, NotificationEvent
from app.models.enums import DeliveryStatus, RegisterKind
from app.services import notifications
from app.services.people import PersonRole
from tests.factories import FakePublisher
from tests.sheets import MANAGER_PHONE, add_row, confirm_manager, connect_drive, row_dict, tab
from tests.whatsapp import deliver, outbound

OWNER = "owner1@example.com"
ANA = "+5511987654321"
CARLOS = "+5511987650000"
PAULA = "+5511911112222"
BRUNO = "+5511976543210"
DORA = "+5511944445555"
JORGE = "+5511933330001"
DEL = RegisterKind.DELIVERIES


@pytest.fixture
def condo(client, db, world, google, publisher):
    connect_drive(client, db, google, world.condo_a, OWNER)
    people = tab(db, google, world.condo_a)
    for zela_id, name, phone, block, unit, role in (
        ("P-ANA", "Ana Souza", ANA, "", "302", "Morador"),
        ("P-CAR", "Carlos Souza", CARLOS, "", "302", "Morador"),
        ("P-PAU", "Paula Lima", PAULA, "", "302", "Proprietária"),
        ("P-BRU", "Bruno Reis", BRUNO, "A", "101", "Proprietário"),
        ("P-DOR", "Dora Melo", DORA, "B", "101", "Moradora"),
        ("P-JOR", "Jorge Silva", JORGE, "", "", "Porteiro"),
    ):
        add_row(
            people,
            zela_id=zela_id,
            name=name,
            whatsapp=phone,
            block=block,
            unit=unit,
            role=role,
        )
    confirm_manager(db, world.condo_a)
    return world.condo_a


@pytest.fixture
def sheet(db, google, condo):
    return tab(db, google, condo, DEL)


@pytest.fixture
def jobs():
    return FakePublisher()


def _say_last(session):
    return say("resultado: " + session.outcomes[-1].content)


def _run(db, condo, google, script, *, phone=JORGE, jobs=None, text="mensagem"):
    llm = ScriptedLLM(script)
    deliver(
        db,
        condo,
        text,
        sender=RecordingSender(),
        llm=llm,
        google=google,
        from_e164=phone,
        publisher=jobs,
    )
    return llm.sessions[0]


def _outcome(session, index=0):
    return json.loads(session.outcomes[index].content)


def _arrivals(db):
    return db.scalars(
        select(NotificationEvent).where(NotificationEvent.template == "zela_delivery_arrived")
    ).all()


def _record(db, condo, google, jobs=None, **args):
    return _run(db, condo, google, [call("record_delivery", **args), _say_last], jobs=jobs)


def test_a_package_is_recorded_and_the_residents_are_told(db, condo, sheet, google, jobs):
    session = _record(db, condo, google, jobs, unit="302", description="Caixa Mercado Livre")
    assert _outcome(session) == {
        "reference": "#1",
        "place": "302",
        "people_notified": 2,
        "recipient_found": False,
    }
    row = row_dict(sheet, 2, DEL)
    assert row["zela_id"].startswith("E-") and row["number"] == "1"
    assert (row["unit"], row["status"], row["received_by"]) == (
        "302",
        "Aguardando retirada",
        "Jorge Silva",
    )
    assert row["received_at"] and row["notified_at"]

    # Residents of 302, not the owner who rents it out.
    alerts = _arrivals(db)
    assert {a.recipient_e164 for a in alerts} == {ANA, CARLOS}
    params = next(a for a in alerts if a.recipient_e164 == ANA).data["params"]
    assert params == {
        "first_name": "Ana",
        "place": "302",
        "description": "Caixa Mercado Livre",
        "number": "1",
    }
    assert len(jobs.take(notifications.NOTIFICATION_TOPIC)) == 2

    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "delivery.received"))
    assert event.data["number"] == "1" and event.data["notified"] == 2
    assert "Mercado" not in json.dumps(event.data) and "302" not in json.dumps(event.data)


def test_only_the_named_recipient_is_told_when_registered(db, condo, sheet, google):
    named = _record(db, condo, google, unit="302", recipient="carlos")
    assert _outcome(named)["recipient_found"] is True
    assert [a.recipient_e164 for a in _arrivals(db)] == [CARLOS]
    assert row_dict(sheet, 2, DEL)["recipient"] == "carlos"

    stranger = _record(db, condo, google, unit="302", recipient="Fernanda Dias")
    assert _outcome(stranger)["recipient_found"] is False
    assert _outcome(stranger)["people_notified"] == 2

    owner = _record(db, condo, google, unit="302", recipient="Paula Lima")
    assert _outcome(owner)["recipient_found"] is True
    assert [a.recipient_e164 for a in _arrivals(db)][-1] == PAULA


def test_blocks_resolve_against_pessoas(db, condo, sheet, google):
    ambiguous = _record(db, condo, google, unit="101")
    assert ambiguous.outcomes[0].is_error and "A, B" in ambiguous.outcomes[0].content
    assert len(sheet.rows) == 1

    # Owner-occupied: no Morador on A 101, so the owner is told.
    owned = _record(db, condo, google, unit="101", block="a")
    assert _outcome(owned)["place"] == "A 101"
    assert [a.recipient_e164 for a in _arrivals(db)] == [BRUNO]
    assert row_dict(sheet, 2, DEL)["block"] == "A"


def test_a_unit_nobody_is_registered_on_is_still_recorded(db, condo, sheet, google):
    session = _record(db, condo, google, unit="999")
    assert _outcome(session)["people_notified"] == 0
    row = row_dict(sheet, 2, DEL)
    assert row["unit"] == "999" and row["notified_at"] == ""
    assert _arrivals(db) == []


def test_a_retried_record_writes_one_row(db, condo, sheet, google):
    args = {"unit": "302", "description": "Envelope"}
    session = _run(
        db,
        condo,
        google,
        [call("record_delivery", **args), call("record_delivery", **args), _say_last],
    )
    assert _outcome(session, 0)["reference"] == _outcome(session, 1)["reference"] == "#1"
    assert _outcome(session, 1)["people_notified"] == 0
    assert len(sheet.rows) == 2 and len(_arrivals(db)) == 2


def test_residents_see_only_their_units_packages(db, condo, sheet, google):
    _record(db, condo, google, unit="302", description="Caixa")
    _record(db, condo, google, unit="101", block="B", description="Envelope")

    refused = _run(db, condo, google, [call("record_delivery", unit="302"), _say_last], phone=ANA)
    assert refused.outcomes[0].is_error and "Unknown tool" in refused.outcomes[0].content
    listing = _run(db, condo, google, [call("find_deliveries"), _say_last], phone=ANA)
    assert listing.outcomes[0].is_error

    mine = _run(db, condo, google, [call("get_my_deliveries"), _say_last], phone=ANA)
    [package] = _outcome(mine)["deliveries"]
    assert package["number"] == "1" and "picked_up_by" not in package

    desk = _run(db, condo, google, [call("find_deliveries", query="envelope"), _say_last])
    assert [d["place"] for d in _outcome(desk)["deliveries"]] == ["B 101"]


def test_staff_close_a_package_by_number(db, condo, sheet, google):
    _record(db, condo, google, unit="302")
    closed = _run(
        db,
        condo,
        google,
        [call("close_delivery", number=1, picked_up_by="Ana"), _say_last],
    )
    assert _outcome(closed)["delivery"]["status"] == "Retirada"
    row = row_dict(sheet, 2, DEL)
    assert (row["status"], row["picked_up_by"]) == ("Retirada", "Ana") and row["picked_up_at"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "delivery.closed"))
    assert event.data == {"register": "deliveries", "number": "1", "outcome": "retirada"}

    mine = _run(db, condo, google, [call("get_my_deliveries"), _say_last], phone=ANA)
    assert _outcome(mine)["deliveries"] == []

    again = _run(db, condo, google, [call("close_delivery", number=1), _say_last])
    assert again.outcomes[0].is_error and "Retirada" in again.outcomes[0].content
    missing = _run(db, condo, google, [call("close_delivery", number=99), _say_last])
    assert missing.outcomes[0].is_error and "#99" in missing.outcomes[0].content


def test_the_manager_can_record_and_return(db, condo, sheet, google):
    _run(
        db,
        condo,
        google,
        [call("record_delivery", unit="302"), _say_last],
        phone=MANAGER_PHONE,
    )
    assert row_dict(sheet, 2, DEL)["received_by"] == "Síndico"
    _run(
        db,
        condo,
        google,
        [call("close_delivery", number=1, outcome="devolvida", note="Endereço errado"), _say_last],
        phone=MANAGER_PHONE,
    )
    row = row_dict(sheet, 2, DEL)
    assert row["status"] == "Devolvida" and row["notes"].endswith("Endereço errado")


def test_the_notice_is_skipped_if_the_package_was_already_picked_up(db, condo, sheet, google):
    _record(db, condo, google, unit="302", recipient="Ana")
    [notice] = _arrivals(db)
    _run(db, condo, google, [call("close_delivery", number=1), _say_last])

    sender = RecordingSender()
    notifications.deliver(db, notice.id, sender, google)
    db.refresh(notice)
    assert notice.status == DeliveryStatus.SKIPPED
    assert sender.sent == [] and sender.templates == []


def test_the_notice_is_sent_while_the_package_waits(db, condo, sheet, google):
    _record(db, condo, google, unit="302", recipient="Ana", description="Caixa")
    [notice] = _arrivals(db)
    sender = RecordingSender()
    notifications.deliver(db, notice.id, sender, google)
    db.refresh(notice)
    assert notice.status != DeliveryStatus.SKIPPED
    [sent] = sender.sent + sender.templates  # a template: Ana hasn't written in 24h
    assert sent[2] == "zela_delivery_arrived" and sent[3] == ["Ana", "302", "Caixa", "1"]


def test_hand_typed_packages(db, condo, sheet, google):
    add_row(sheet, DEL, number="5", unit="302", description="Sacola")  # no status typed
    mine = _run(db, condo, google, [call("get_my_deliveries"), _say_last], phone=CARLOS)
    assert [d["number"] for d in _outcome(mine)["deliveries"]] == ["5"]

    _run(db, condo, google, [call("close_delivery", number=5), _say_last])
    row = row_dict(sheet, 2, DEL)
    assert row["zela_id"] == "E-ROW2" and row["status"] == "Retirada"


@pytest.mark.parametrize(
    ("role", "desk"),
    [
        (PersonRole.RESIDENT, False),
        (PersonRole.OWNER, False),
        (PersonRole.STAFF, True),
        (PersonRole.MANAGER, True),
    ],
)
def test_delivery_tools_by_role(role, desk):
    names = {s.name for s in zela.build_registry(role).specs()}
    assert "get_my_deliveries" in names
    assert ({"record_delivery", "find_deliveries", "close_delivery"} <= names) is desk
    assert ("register_person" in names) is (role == PersonRole.MANAGER)


def test_the_dev_stand_in_handles_the_readme_phrasing(db, condo, sheet, google):
    def say_(phone, text):
        deliver(
            db,
            condo,
            text,
            sender=RecordingSender(),
            llm=RuleBasedLLM(),
            google=google,
            from_e164=phone,
        )
        return outbound(db)[-1].body

    assert "#1 registrada para B 101" in say_(JORGE, "chegou encomenda pro 101 bloco B")
    assert "#1 B 101" in say_(DORA, "tem encomenda pra mim?")
    assert "Retirada" in say_(JORGE, "encomenda #1 retirada pela Dora")
    assert row_dict(sheet, 2, DEL)["picked_up_by"] == "Dora"
    assert "Nenhuma encomenda" in say_(JORGE, "encomendas pendentes")
