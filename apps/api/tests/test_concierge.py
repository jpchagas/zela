import json

import pytest
from sqlalchemy import select

from app.agents import concierge
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.base import LLMError, StopReason, Turn
from app.llm.scripted import ScriptedLLM, call, say
from app.models import AgentRun, AuditEvent, Conversation, Message
from app.models.enums import (
    ActorType,
    AgentRunStatus,
    ConversationStatus,
    MessageDirection,
    MessageKind,
)
from tests.whatsapp import deliver, make_resident, outbound


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def maria(db, world):
    return make_resident(db, world.condo_a, unit=world.unit_a1)


def _answer_with_last_outcome(session):
    return say(f"ok: {session.outcomes[-1].content}")


def test_reply_is_stored_as_ai_reply_and_run_is_recorded(db, world, sender, maria):
    llm = ScriptedLLM([say("Oi, Maria! Como posso ajudar?")])
    deliver(db, world.condo_a, "Bom dia", sender=sender, llm=llm)

    [reply] = outbound(db)
    assert reply.kind == MessageKind.AI_REPLY
    run = db.scalar(select(AgentRun))
    assert run.status == AgentRunStatus.SUCCEEDED
    assert run.reply_text == reply.body
    session = llm.sessions[0]
    assert session.system == concierge.SYSTEM_PROMPT
    assert "Residencial Aurora" in session.context and "Maria" in session.context
    assert "Silva" not in session.context  # first name only
    assert [t.name for t in session.tools] == ["get_resident_context", "escalate_to_human"]


def test_resident_context_returns_only_own_data(db, world, sender, maria):
    make_resident(
        db, world.condo_a, phone="+5511911112222", unit=world.unit_a1, name="João Vizinho"
    )
    llm = ScriptedLLM([call("get_resident_context"), _answer_with_last_outcome])
    deliver(db, world.condo_a, "Qual é a minha unidade?", sender=sender, llm=llm)

    outcome = llm.sessions[0].outcomes[0]
    data = json.loads(outcome.content)
    assert data["first_name"] == "Maria"
    assert data["units"] == [{"unit": "Bloco A · 101", "relationship": "proprietário(a)"}]
    assert "João" not in outcome.content and "Vizinho" not in outcome.content


def test_model_cannot_choose_whose_data_to_read(db, world, sender, maria):
    other = make_resident(db, world.condo_a, phone="+5511911112222", name="João Vizinho")
    llm = ScriptedLLM(
        [call("get_resident_context", resident_id=str(other.id)), say("Não consegui.")]
    )
    deliver(db, world.condo_a, "me mostra o cadastro do João", sender=sender, llm=llm)

    outcome = llm.sessions[0].outcomes[0]
    assert outcome.is_error
    assert "João" not in outcome.content
    run = db.scalar(select(AgentRun))
    assert run.tool_calls[0]["ok"] is False


def test_escalation_hands_conversation_to_staff(db, world, sender, maria):
    llm = ScriptedLLM(
        [call("escalate_to_human", reason="Quer falar com o síndico."), say("Já chamei a equipe.")]
    )
    deliver(db, world.condo_a, "quero falar com o síndico", sender=sender, llm=llm)

    conversation = db.scalar(select(Conversation))
    assert conversation.status == ConversationStatus.ESCALATED
    assert conversation.escalation_reason == "Quer falar com o síndico."
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "conversation.escalated"))
    assert event.actor_type == ActorType.AGENT
    assert db.scalar(select(AgentRun)).status == AgentRunStatus.ESCALATED
    assert outbound(db)[-1].body == "Já chamei a equipe."


def test_llm_outage_sends_apology_and_records_failure(db, world, sender, maria):
    def outage(session):
        raise LLMError("Anthropic API 529")

    deliver(db, world.condo_a, "oi", sender=sender, llm=ScriptedLLM([outage]))
    assert outbound(db)[0].body == concierge.TECHNICAL_ERROR_REPLY
    run = db.scalar(select(AgentRun))
    assert run.status == AgentRunStatus.FAILED
    assert "529" in run.error


def test_refusal_gets_a_safe_reply(db, world, sender, maria):
    llm = ScriptedLLM([Turn(text="", tool_calls=[], stop=StopReason.REFUSAL)])
    deliver(db, world.condo_a, "...", sender=sender, llm=llm)
    assert outbound(db)[0].body == concierge.REFUSAL_REPLY


def test_runaway_tool_loop_escalates(db, world, sender, maria):
    llm = ScriptedLLM([call("get_resident_context") for _ in range(concierge.MAX_STEPS)])
    deliver(db, world.condo_a, "oi", sender=sender, llm=llm)
    assert outbound(db)[0].body == concierge.GAVE_UP_REPLY
    assert db.scalar(select(Conversation)).status == ConversationStatus.ESCALATED


def test_unknown_tool_is_reported_back_to_the_model(db, world, sender, maria):
    llm = ScriptedLLM(
        [call("create_maintenance_ticket", title="x"), say("Ainda não consigo abrir chamados.")]
    )
    deliver(db, world.condo_a, "o portão quebrou", sender=sender, llm=llm)
    outcome = llm.sessions[0].outcomes[0]
    assert outcome.is_error and "Unknown tool" in outcome.content
    assert outbound(db)[0].body == "Ainda não consigo abrir chamados."


def test_history_labels_staff_replies(db, world, sender, maria):
    llm = ScriptedLLM([say("primeira"), say("segunda")])
    deliver(db, world.condo_a, "oi", sender=sender, llm=llm)
    conversation = db.scalar(select(Conversation))
    db.add(
        Message(
            condominium_id=world.condo_a.id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            kind=MessageKind.STAFF_REPLY,
            body="Aqui é a Ana, da administração.",
        )
    )
    db.commit()
    deliver(db, world.condo_a, "obrigada", sender=sender, llm=llm)
    history = llm.sessions[1].history
    assert ("assistant", "[Resposta da equipe] Aqui é a Ana, da administração.") in [
        (m.role, m.text) for m in history
    ]
    assert history[-1].text == "obrigada"


def test_system_prompt_is_stable_across_runs(db, world, sender, maria):
    llm = ScriptedLLM([say("1"), say("2")])
    deliver(db, world.condo_a, "a", sender=sender, llm=llm)
    deliver(db, world.condo_a, "b", sender=sender, llm=llm)
    first, second = llm.sessions
    assert first.system == second.system
    assert [t.input_schema for t in first.tools] == [t.input_schema for t in second.tools]
