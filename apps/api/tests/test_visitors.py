"""Visitors over WhatsApp in the Visitantes sheet (ADR 0014)."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import RuleBasedLLM, ScriptedLLM, call, say
from app.models import AuditEvent, NotificationEvent
from app.models.enums import DeliveryStatus, RegisterKind
from app.services import notifications, visitors
from tests.factories import FakePublisher
from tests.sheets import MANAGER_PHONE, add_row, confirm_manager, connect_drive, row_dict, tab
from tests.whatsapp import deliver, outbound

OWNER = "owner1@example.com"
ANA = "+5511987654321"
CARLOS = "+5511987650000"
BRUNO = "+5511976543210"
JORGE = "+5511933330001"
VIS = RegisterKind.VISITORS


@pytest.fixture
def condo(client, db, world, google, publisher):
    connect_drive(client, db, google, world.condo_a, OWNER)
    people = tab(db, google, world.condo_a)
    for zela_id, name, phone, block, unit, role in (
        ("P-ANA", "Ana Souza", ANA, "", "302", "Morador"),
        ("P-CAR", "Carlos Souza", CARLOS, "", "302", "Morador"),
        ("P-B1", "Bruno Reis", BRUNO, "A", "101", "Proprietário"),
        ("P-B2", "Bruno Reis", BRUNO, "B", "202", "Proprietário"),
        ("P-JOR", "Jorge Silva", JORGE, "", "", "Porteiro"),
    ):
        add_row(
            people, zela_id=zela_id, name=name, whatsapp=phone, block=block, unit=unit, role=role
        )
    confirm_manager(db, world.condo_a)
    return world.condo_a


@pytest.fixture
def sheet(db, google, condo):
    return tab(db, google, condo, VIS)


@pytest.fixture
def day(condo):
    return visitors.today(condo)


def _say_last(session):
    return say("resultado: " + session.outcomes[-1].content)


def _run(db, condo, google, script, *, phone=ANA, jobs=None, text="mensagem"):
    llm = ScriptedLLM(script)
    deliver(
        db,
        condo,
        text,
        sender=RecordingSender(),
        llm=llm,
        google=google,
        from_e164=phone,
        publisher=jobs or FakePublisher(),
    )
    return llm.sessions[0]


def _outcome(session, index=0):
    return json.loads(session.outcomes[index].content)


def _error(session, index=0):
    assert session.outcomes[index].is_error, session.outcomes[index].content
    return session.outcomes[index].content


def _sent(db, template):
    return db.scalars(
        select(NotificationEvent)
        .where(NotificationEvent.template == template)
        .order_by(NotificationEvent.created_at)
    ).all()


def _authorize(db, condo, google, phone=ANA, **args):
    """Both steps, in two messages; returns the code."""
    _run(db, condo, google, [call("authorize_visitor", **args), _say_last], phone=phone)
    done = _run(
        db,
        condo,
        google,
        [call("authorize_visitor", **args, confirmed=True), _say_last],
        phone=phone,
    )
    return _outcome(done)["code"]


def test_a_resident_authorizes_in_two_steps(db, condo, sheet, google, day):
    args = {"visitor_name": "Marcos Lima", "visit_date": str(day + timedelta(days=1))}
    blind = _run(db, condo, google, [call("authorize_visitor", **args, confirmed=True), _say_last])
    assert "confirmed=false" in _error(blind)

    preview = _run(db, condo, google, [call("authorize_visitor", **args), _say_last])
    assert _outcome(preview)["summary"] == {
        "visitor": "Marcos Lima",
        "place": "302",
        "visit_date": visitors.fmt(day + timedelta(days=1)),
        "valid_until": visitors.fmt(day + timedelta(days=1)),
        "notes": "",
    }
    assert len(sheet.rows) == 1

    done = _run(db, condo, google, [call("authorize_visitor", **args, confirmed=True), _say_last])
    code = _outcome(done)["code"]
    assert len(code) == 6 and code.isdigit()
    row = row_dict(sheet, 2, VIS)
    assert (row["code"], row["visitor"], row["unit"], row["status"]) == (
        code,
        "Marcos Lima",
        "302",
        "Autorizado",
    )
    assert (row["authorized_by"], row["authorized_by_id"]) == ("Ana Souza (302)", "P-ANA")
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "visitor.authorized"))
    assert event.data["days"] == 1 and "Marcos" not in json.dumps(event.data)


@pytest.mark.parametrize(
    ("first", "last", "message"),
    [
        (-1, None, "past"),
        (61, None, "60 days"),
        (2, 1, "before the first"),
        (0, 31, "30 days"),
    ],
)
def test_authorization_dates_are_checked(db, condo, google, day, first, last, message):
    args = {"visitor_name": "Marcos", "visit_date": str(day + timedelta(days=first))}
    if last is not None:
        args["last_day"] = str(day + timedelta(days=last))
    session = _run(db, condo, google, [call("authorize_visitor", **args), _say_last])
    assert message in _error(session)


def test_the_unit_comes_from_the_senders_rows(db, condo, sheet, google, day):
    args = {"visitor_name": "Marcos", "visit_date": str(day)}
    assert "A 101, B 202" in _error(
        _run(db, condo, google, [call("authorize_visitor", **args), _say_last], phone=BRUNO)
    )
    not_theirs = _run(
        db, condo, google, [call("authorize_visitor", **args, unit="302"), _say_last], phone=BRUNO
    )
    assert "not one of the sender's units" in _error(not_theirs)

    _authorize(db, condo, google, phone=BRUNO, **args, unit="202")
    assert (row_dict(sheet, 2, VIS)["block"], row_dict(sheet, 2, VIS)["unit"]) == ("B", "202")

    # The manager may authorize for any unit, or for the condominium itself.
    _authorize(
        db, condo, google, phone=MANAGER_PHONE, visitor_name="Eletricista", visit_date=str(day)
    )
    row = row_dict(sheet, 3, VIS)
    assert row["unit"] == "" and row["authorized_by_id"] == "SINDICO"
    _authorize(db, condo, google, phone=MANAGER_PHONE, **args, unit="302")
    assert row_dict(sheet, 4, VIS)["unit"] == "302"


def test_tools_follow_the_role(db, condo, google, day):
    staff = _run(
        db,
        condo,
        google,
        [call("authorize_visitor", visitor_name="Marcos", visit_date=str(day)), _say_last],
        phone=JORGE,
    )
    assert "Unknown tool" in _error(staff)
    for name, args in (
        ("check_visitor", {}),
        ("announce_visitor", {"visitor_name": "Marcos", "unit": "302"}),
        ("record_visitor_entry", {"code": "123456"}),
    ):
        resident = _run(db, condo, google, [call(name, **args), _say_last])
        assert "Unknown tool" in _error(resident)


def test_the_desk_lets_an_authorized_visitor_in(db, condo, sheet, google, day):
    code = _authorize(db, condo, google, visitor_name="Marcos Lima", visit_date=str(day))
    found = _run(db, condo, google, [call("check_visitor", query="marcos"), _say_last], phone=JORGE)
    [visitor] = _outcome(found)["visitors"]
    assert (visitor["code"], visitor["place"], visitor["status"]) == (code, "302", "Autorizado")
    assert "authorized_by" not in visitor

    jobs = FakePublisher()
    entry = _run(
        db,
        condo,
        google,
        [call("record_visitor_entry", code=code), _say_last],
        phone=JORGE,
        jobs=jobs,
    )
    assert _outcome(entry)["authorizer_told"] is True
    row = row_dict(sheet, 2, VIS)
    assert (row["status"], row["checked_by"]) == ("Entrou", "Jorge Silva") and row["entered_at"]
    [arrived] = _sent(db, "zela_visitor_arrived")
    assert arrived.recipient_e164 == ANA and arrived.data["params"]["code"] == code
    assert len(jobs.take(notifications.NOTIFICATION_TOPIC)) == 1

    again = _run(
        db, condo, google, [call("record_visitor_entry", code=code), _say_last], phone=JORGE
    )
    assert "not valid today: Entrou" in _error(again)


def test_a_multi_day_authorization_stays_valid(db, condo, sheet, google, day):
    code = _authorize(
        db,
        condo,
        google,
        visitor_name="Rosa (diarista)",
        visit_date=str(day),
        last_day=str(day + timedelta(days=4)),
    )
    for _ in range(2):
        _run(db, condo, google, [call("record_visitor_entry", code=code), _say_last], phone=JORGE)
    row = row_dict(sheet, 2, VIS)
    assert row["status"] == "Autorizado" and row["notes"].count("Entrada em") == 2
    assert len(_sent(db, "zela_visitor_arrived")) == 2


def test_only_todays_authorizations_open_the_gate(db, condo, sheet, google, day):
    tomorrow = _authorize(
        db, condo, google, visitor_name="Marcos", visit_date=str(day + timedelta(days=1))
    )
    add_row(
        sheet,
        VIS,
        code="654321",
        visitor="Paulo",
        unit="302",
        visit_date=visitors.fmt(day - timedelta(days=2)),
        valid_until=visitors.fmt(day - timedelta(days=1)),
        status="Autorizado",  # never updated by hand
    )
    found = _run(db, condo, google, [call("check_visitor"), _say_last], phone=JORGE)
    assert _outcome(found)["visitors"] == []
    future = _run(
        db, condo, google, [call("record_visitor_entry", code=tomorrow), _say_last], phone=JORGE
    )
    assert "Autorizado" in _error(future)
    expired = _run(
        db, condo, google, [call("record_visitor_entry", code="654321"), _say_last], phone=JORGE
    )
    assert "Expirado" in _error(expired)

    mine = _run(db, condo, google, [call("get_my_visitors"), _say_last])
    assert [v["code"] for v in _outcome(mine)["visitors"]] == [tomorrow]


def test_an_unannounced_visitor_is_let_in_by_the_unit(db, condo, sheet, google):
    jobs = FakePublisher()
    announced = _run(
        db,
        condo,
        google,
        [call("announce_visitor", visitor_name="Marcos", unit="302", notes="técnico"), _say_last],
        phone=JORGE,
        jobs=jobs,
    )
    result = _outcome(announced)
    code = result["code"]
    assert result["people_asked"] == 2 and result["place"] == "302"
    row = row_dict(sheet, 2, VIS)
    assert (row["status"], row["checked_by_id"]) == ("Aguardando morador", "P-JOR")
    asks = _sent(db, "zela_visitor_at_gate")
    assert {a.recipient_e164 for a in asks} == {ANA, CARLOS}
    assert asks[0].data["params"]["code"] == code

    answered = _run(
        db, condo, google, [call("answer_visitor", code=code, allow=True), _say_last], phone=CARLOS
    )
    assert _outcome(answered)["desk_told"] is True
    row = row_dict(sheet, 2, VIS)
    assert (row["status"], row["authorized_by_id"]) == ("Autorizado", "P-CAR")
    [answer] = _sent(db, "zela_visitor_answer")
    assert answer.recipient_e164 == JORGE and answer.data["params"]["answer"] == "liberou"

    late = _run(db, condo, google, [call("answer_visitor", code=code, allow=False), _say_last])
    assert "not waiting for an answer" in _error(late)

    # Ana's question is skipped if it hadn't gone out yet: Carlos already answered.
    ana_ask = next(a for a in asks if a.recipient_e164 == ANA)
    notifications.deliver(db, ana_ask.id, RecordingSender(), google)
    db.refresh(ana_ask)
    assert ana_ask.status == DeliveryStatus.SKIPPED

    entry = _run(
        db, condo, google, [call("record_visitor_entry", code=code), _say_last], phone=JORGE
    )
    assert _outcome(entry)["authorizer_told"] is False  # Carlos just answered
    assert row_dict(sheet, 2, VIS)["status"] == "Entrou"


def test_a_refused_visitor_stays_out(db, condo, sheet, google):
    announced = _run(
        db,
        condo,
        google,
        [call("announce_visitor", visitor_name="Desconhecido", unit="302"), _say_last],
        phone=JORGE,
    )
    code = _outcome(announced)["code"]
    _run(db, condo, google, [call("answer_visitor", code=code, allow=False), _say_last])
    assert row_dict(sheet, 2, VIS)["status"] == "Recusado"
    assert _sent(db, "zela_visitor_answer")[0].data["params"]["answer"] == "não liberou"
    entry = _run(
        db, condo, google, [call("record_visitor_entry", code=code), _say_last], phone=JORGE
    )
    assert "Recusado" in _error(entry)


def test_other_units_cannot_answer_or_cancel(db, condo, sheet, google, day):
    announced = _run(
        db,
        condo,
        google,
        [call("announce_visitor", visitor_name="Marcos", unit="302"), _say_last],
        phone=JORGE,
    )
    code = _outcome(announced)["code"]
    stranger = _run(
        db, condo, google, [call("answer_visitor", code=code, allow=True), _say_last], phone=BRUNO
    )
    missing = _run(
        db, condo, google, [call("answer_visitor", code="999999", allow=True), _say_last]
    )
    # A code of another unit reads exactly like one that doesn't exist.
    assert _error(stranger).replace(code, "X") == _error(missing).replace("999999", "X")
    assert row_dict(sheet, 2, VIS)["status"] == "Aguardando morador"

    authorized = _authorize(db, condo, google, visitor_name="Paula", visit_date=str(day))
    refused = _run(
        db, condo, google, [call("cancel_visitor", code=authorized), _say_last], phone=BRUNO
    )
    assert "no authorization" in _error(refused)
    _run(db, condo, google, [call("cancel_visitor", code=authorized), _say_last])
    assert row_dict(sheet, 3, VIS)["status"] == "Cancelado"


def test_the_manager_can_cancel_any_authorization(db, condo, sheet, google, day):
    code = _authorize(db, condo, google, visitor_name="Paula", visit_date=str(day))
    _run(db, condo, google, [call("cancel_visitor", code=code), _say_last], phone=MANAGER_PHONE)
    assert row_dict(sheet, 2, VIS)["status"] == "Cancelado"
    again = _run(db, condo, google, [call("cancel_visitor", code=code), _say_last])
    assert "Cancelado" in _error(again)


def test_a_retried_authorization_writes_one_row(db, condo, sheet, google, day):
    args = {"visitor_name": "Marcos", "visit_date": str(day)}
    _run(db, condo, google, [call("authorize_visitor", **args), _say_last])
    done = _run(
        db,
        condo,
        google,
        [
            call("authorize_visitor", **args, confirmed=True),
            call("authorize_visitor", **args, confirmed=True),
            _say_last,
        ],
    )
    assert _outcome(done, 0)["code"] == _outcome(done, 1)["code"]
    assert len(sheet.rows) == 2


def test_the_gate_notice_reaches_the_agent_as_context(db, condo, sheet, google):
    """The notice may be the first message in the resident's conversation; the model must
    still see it when the resident answers."""
    announced = _run(
        db,
        condo,
        google,
        [call("announce_visitor", visitor_name="Marcos", unit="302"), _say_last],
        phone=JORGE,
    )
    code = _outcome(announced)["code"]
    ask = next(a for a in _sent(db, "zela_visitor_at_gate") if a.recipient_e164 == ANA)
    notifications.deliver(db, ask.id, RecordingSender(), google)

    session = _run(db, condo, google, [say("ok")], text="pode subir")
    assert session.history[0].role == "user"
    assert any(code in m.text and m.role == "assistant" for m in session.history)


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

    assert "Confere?" in say_(ANA, "autorizar visita de Marcos Lima hoje")
    assert "Código" in say_(ANA, "sim")
    code = row_dict(sheet, 2, VIS)["code"]
    assert code in say_(JORGE, "visitante Marcos")
    assert "entrada registrada" in say_(JORGE, f"entrada {code}").lower()

    assert "perguntei" in say_(JORGE, "anunciar Paulo pro 302").lower()
    ask = next(a for a in _sent(db, "zela_visitor_at_gate") if a.recipient_e164 == CARLOS)
    notifications.deliver(db, ask.id, RecordingSender(), google)
    assert "portaria" in say_(CARLOS, "sim").lower()
    assert row_dict(sheet, 3, VIS)["status"] == "Autorizado"
