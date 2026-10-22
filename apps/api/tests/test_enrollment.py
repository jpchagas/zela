from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.integrations.whatsapp.sender import RecordingSender
from app.models import AuditEvent, Conversation, EnrollmentCode, Resident, ResidentPhone
from app.models.enums import ActorType, MessageKind, ResidentStatus
from app.services.enrollment import MAX_FAILED_ATTEMPTS
from app.workers import inbound as msgs
from tests.factories import auth
from tests.whatsapp import RESIDENT_PHONE, deliver, outbound

MANAGER = auth("manager.a@example.com")


@pytest.fixture
def sender():
    return RecordingSender()


def _register(client, world, phone="11987654321"):
    r = client.post(
        f"/v1/condominiums/{world.condo_a.id}/residents",
        json={"full_name": "Maria Silva", "phones": [{"number": phone}]},
        headers=MANAGER,
    ).json()
    return r, r["phones"][0]["id"]


def _issue(client, world, resident_id, phone_id, headers=MANAGER):
    return client.post(
        f"/v1/condominiums/{world.condo_a.id}/residents/{resident_id}/phones/{phone_id}/enrollment-code",
        headers=headers,
    )


def test_manager_issues_code_shown_once(client, db, world):
    resident, phone_id = _register(client, world)
    response = _issue(client, world, resident["id"], phone_id)
    assert response.status_code == 201
    body = response.json()
    assert len(body["code"]) == 9 and body["code"][4] == "-"
    assert body["phone_e164"] == RESIDENT_PHONE
    stored = db.scalar(select(EnrollmentCode))
    assert body["code"].replace("-", "") not in stored.code_hash
    assert db.scalar(
        select(AuditEvent).where(AuditEvent.action == "resident.enrollment_code_issued")
    )


def test_issuing_requires_manage_permission_and_own_condominium(client, world):
    resident, phone_id = _register(client, world)
    assert (
        _issue(client, world, resident["id"], phone_id, auth("staff.a@example.com")).status_code
        == 403
    )
    assert (
        _issue(client, world, resident["id"], phone_id, auth("manager.b@example.com")).status_code
        == 404
    )


def test_full_enrollment_over_whatsapp(client, db, world, sender):
    resident, phone_id = _register(client, world)
    code = _issue(client, world, resident["id"], phone_id).json()["code"]

    deliver(db, world.condo_a, f"oi, meu código é {code.lower()}", sender=sender)

    db.expire_all()
    assert db.get(Resident, resident["id"]).status == ResidentStatus.ACTIVE
    assert db.scalar(select(ResidentPhone)).verified_at is not None
    assert db.scalar(select(Conversation)).resident_id is not None
    [reply] = outbound(db)
    assert reply.kind == MessageKind.SYSTEM_REPLY
    assert reply.body.startswith("Pronto, Maria!")
    assert sender.sent[0][1] == RESIDENT_PHONE
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "resident.enrolled"))
    assert event.actor_type == ActorType.RESIDENT


def test_code_sent_from_another_number_does_not_enroll(client, db, world, sender):
    resident, phone_id = _register(client, world)
    code = _issue(client, world, resident["id"], phone_id).json()["code"]

    deliver(db, world.condo_a, code, sender=sender, from_e164="+5511900001111")

    db.expire_all()
    assert db.get(Resident, resident["id"]).status == ResidentStatus.INVITED
    assert outbound(db)[0].body == msgs.UNKNOWN_NUMBER.format(condo="Residencial Aurora")


def test_wrong_codes_lock_the_code(client, db, world, sender):
    resident, phone_id = _register(client, world)
    code = _issue(client, world, resident["id"], phone_id).json()["code"]
    for _ in range(MAX_FAILED_ATTEMPTS):
        deliver(db, world.condo_a, "ZZZZ-ZZZZ", sender=sender)
    deliver(db, world.condo_a, code, sender=sender)

    replies = [m.body for m in outbound(db)]
    assert replies[: MAX_FAILED_ATTEMPTS - 1] == [msgs.WRONG_CODE] * (MAX_FAILED_ATTEMPTS - 1)
    assert replies[MAX_FAILED_ATTEMPTS - 1 :] == [msgs.CODE_UNUSABLE] * 2
    db.expire_all()
    assert db.get(Resident, resident["id"]).status == ResidentStatus.INVITED


def test_expired_code_is_rejected(client, db, world, sender):
    resident, phone_id = _register(client, world)
    code = _issue(client, world, resident["id"], phone_id).json()["code"]
    pending = db.scalar(select(EnrollmentCode))
    pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    deliver(db, world.condo_a, code, sender=sender)
    assert outbound(db)[0].body == msgs.CODE_UNUSABLE


def test_new_code_replaces_the_previous_one(client, db, world, sender):
    resident, phone_id = _register(client, world)
    old = _issue(client, world, resident["id"], phone_id).json()["code"]
    new = _issue(client, world, resident["id"], phone_id).json()["code"]

    deliver(db, world.condo_a, old, sender=sender)
    deliver(db, world.condo_a, new, sender=sender)

    assert [m.body for m in outbound(db)][0] == msgs.WRONG_CODE
    assert outbound(db)[1].body.startswith("Pronto")


def test_unenrolled_sender_is_asked_for_code_without_calling_the_model(client, db, world, sender):
    _register(client, world)
    # ScriptedLLM with an empty script raises if the model is ever called.
    deliver(db, world.condo_a, "Qual o horário da piscina?", sender=sender)
    assert outbound(db)[0].body == msgs.ASK_FOR_CODE


def test_suspended_resident_cannot_enroll(client, db, world, sender):
    resident, phone_id = _register(client, world)
    code = _issue(client, world, resident["id"], phone_id).json()["code"]
    client.post(
        f"/v1/condominiums/{world.condo_a.id}/residents/{resident['id']}/suspend", headers=MANAGER
    )

    deliver(db, world.condo_a, code, sender=sender)
    assert outbound(db)[0].body == msgs.ACCESS_SUSPENDED
    assert db.scalar(select(ResidentPhone)).verified_at is None
