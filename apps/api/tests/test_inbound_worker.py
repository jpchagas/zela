from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import ScriptedLLM, say
from app.models import AgentRun, Conversation, Message, WebhookEvent
from app.models.enums import ConversationStatus, DeliveryStatus, JobStatus, MessageKind
from app.services import conversations
from app.workers import inbound as msgs
from app.workers.inbound import process_webhook_event
from tests.whatsapp import deliver, make_resident, outbound


@pytest.fixture
def sender():
    return RecordingSender()


def test_unroutable_event_is_marked_failed(db, world, sender):
    unknown = SimpleNamespace(whatsapp_phone_number_id="999")
    [event_id] = deliver(db, unknown, "oi", sender=sender)
    db.expire_all()
    event = db.get(WebhookEvent, event_id)
    assert event.status == JobStatus.FAILED
    assert "phone_number_id" in event.error
    assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_reprocessing_an_event_does_not_rerun_agent_or_resend(db, world, sender):
    make_resident(db, world.condo_a)
    llm = ScriptedLLM([say("Olá, Maria!")])
    [event_id] = deliver(db, world.condo_a, "oi", sender=sender, llm=llm)

    # Simulate a redelivery after a crash right before the event was marked processed.
    event = db.get(WebhookEvent, event_id)
    event.status = JobStatus.RECEIVED
    db.commit()
    process_webhook_event(db, event_id, llm=llm, sender=sender)

    assert len(llm.sessions) == 1
    assert len(sender.sent) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert [m.body for m in outbound(db)] == ["Olá, Maria!"]


def test_reply_left_pending_by_a_crash_is_sent_on_retry(db, world):
    make_resident(db, world.condo_a)
    llm = ScriptedLLM([say("Resposta")])

    class Crashing:
        def send_text(self, *args):
            raise RuntimeError("worker died mid-send")

    with pytest.raises(RuntimeError):
        deliver(db, world.condo_a, "oi", sender=Crashing(), llm=llm)
    event = db.scalar(select(WebhookEvent))
    assert event.status == JobStatus.FAILED
    assert outbound(db)[0].delivery_status == DeliveryStatus.PENDING

    working = RecordingSender()
    process_webhook_event(db, event.id, llm=llm, sender=working)
    assert len(working.sent) == 1
    assert outbound(db)[0].delivery_status == DeliveryStatus.SENT
    assert len(llm.sessions) == 1


def test_provider_rejection_is_recorded_on_the_message(db, world):
    make_resident(db, world.condo_a)
    deliver(
        db,
        world.condo_a,
        "oi",
        sender=RecordingSender(fail_with="WhatsApp API 400: bad number"),
        llm=ScriptedLLM([say("Olá")]),
    )
    [reply] = outbound(db)
    assert reply.delivery_status == DeliveryStatus.FAILED
    assert "bad number" in reply.delivery_error
    assert db.scalar(select(WebhookEvent)).status == JobStatus.PROCESSED


def test_delivery_statuses_only_move_forward(db, world, sender):
    make_resident(db, world.condo_a)
    deliver(db, world.condo_a, "oi", sender=sender, llm=ScriptedLLM([say("Olá")]))
    reply = outbound(db)[0]
    pid = reply.provider_message_id

    for status in ("delivered", "read", "sent", "failed"):
        conversations.apply_delivery_status(db, pid, status)
    db.refresh(reply)
    assert reply.delivery_status == DeliveryStatus.READ


def test_media_message_gets_text_only_reply_without_model(db, world, sender):
    make_resident(db, world.condo_a)
    deliver(db, world.condo_a, None, sender=sender, msg_type="image")
    assert outbound(db)[0].body == msgs.TEXT_ONLY
    inbound = db.scalar(select(Message).where(Message.kind == MessageKind.RESIDENT))
    assert inbound.body == "[image]"


def test_escalated_conversation_is_left_to_staff(db, world, sender):
    make_resident(db, world.condo_a)
    deliver(db, world.condo_a, "oi", sender=sender, llm=ScriptedLLM([say("Olá")]))
    conversation = db.scalar(select(Conversation))
    conversation.status = ConversationStatus.ESCALATED
    db.commit()

    deliver(db, world.condo_a, "alguém aí?", sender=sender)  # empty script: model not called
    assert len(outbound(db)) == 1
    assert (
        db.scalar(
            select(func.count()).select_from(Message).where(Message.kind == MessageKind.RESIDENT)
        )
        == 2
    )


def test_messages_from_one_contact_share_a_conversation(db, world, sender):
    make_resident(db, world.condo_a)
    llm = ScriptedLLM([say("1"), say("2")])
    deliver(db, world.condo_a, "oi", sender=sender, llm=llm)
    deliver(db, world.condo_a, "tudo bem?", sender=sender, llm=llm)
    assert db.scalar(select(func.count()).select_from(Conversation)) == 1
    # The second run sees the first exchange as history.
    assert [m.text for m in llm.sessions[1].history] == ["oi", "1", "tudo bem?"]
