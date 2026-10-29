"""The concierge: one orchestrated agent run per inbound message from an enrolled
resident (PDD §6.1). Capabilities grow by adding tools to the registry."""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.resident_tools import build_resident_registry
from app.agents.tools import ToolContext, ToolError, ToolRegistry
from app.core.jobs import JobPublisher, get_job_publisher
from app.llm.base import ChatMessage, LLMClient, LLMError, StopReason, ToolCall, ToolOutcome, Usage
from app.models import AgentRun, Condominium, Conversation, Message, Resident
from app.models.enums import ActorType, AgentRunStatus, ConversationStatus, MessageKind
from app.services import conversations

logger = logging.getLogger(__name__)

MAX_STEPS = 6
HISTORY_LIMIT = 20

# Byte-identical across runs so the provider can cache it. Per-run facts go in the
# context block (render_context), never here.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "concierge_system.md").read_text(
    encoding="utf-8"
)

TECHNICAL_ERROR_REPLY = (
    "Desculpe, tive um problema técnico agora e não consegui responder. "
    "Pode tentar de novo em alguns instantes?"
)
REFUSAL_REPLY = (
    "Não consigo ajudar com isso por aqui. Se quiser, posso encaminhar sua mensagem para a "
    "equipe do condomínio."
)
GAVE_UP_REPLY = (
    "Não consegui concluir seu pedido. Encaminhei a conversa para a equipe do condomínio, "
    "que vai responder aqui."
)

_ROLE_BY_KIND = {
    MessageKind.RESIDENT: ("user", ""),
    MessageKind.AI_REPLY: ("assistant", ""),
    MessageKind.SYSTEM_REPLY: ("assistant", ""),
    MessageKind.STAFF_REPLY: ("assistant", "[Resposta da equipe] "),
    MessageKind.NOTIFICATION: ("assistant", "[Aviso automático] "),
    MessageKind.ANNOUNCEMENT: ("assistant", "[Comunicado da administração] "),
}


def render_context(condominium: Condominium, resident: Resident, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(condominium.timezone))
    return (
        f"Condomínio: {condominium.name}\n"
        f"Morador identificado nesta conversa: {resident.full_name.split()[0]}\n"
        f"Data e hora local: {local:%d/%m/%Y %H:%M}"
    )


def load_history(db: Session, conversation: Conversation) -> list[ChatMessage]:
    recent = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.redacted_at.is_(None),
            Message.body.is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = []
    for message in reversed(recent):
        role, prefix = _ROLE_BY_KIND[message.kind]
        history.append(ChatMessage(role=role, text=prefix + message.body))
    while history and history[0].role != "user":
        history.pop(0)  # the provider requires the first turn to be the user's
    return history


def run_concierge(
    db: Session,
    llm: LLMClient,
    *,
    condominium: Condominium,
    conversation: Conversation,
    resident: Resident,
    trigger: Message,
    registry: ToolRegistry | None = None,
    publisher: JobPublisher | None = None,
) -> AgentRun:
    """The Milestone 2–3 concierge for an enrolled resident (Postgres records)."""
    return run_agent(
        db,
        llm,
        agent="concierge",
        condominium=condominium,
        conversation=conversation,
        trigger=trigger,
        system=SYSTEM_PROMPT,
        context=render_context(condominium, resident, datetime.now(timezone.utc)),
        registry=registry or build_resident_registry(),
        make_context=lambda run_id: ToolContext(
            condominium_id=condominium.id,
            resident_id=resident.id,
            conversation_id=conversation.id,
            agent_run_id=run_id,
            idempotency_key=f"msg:{trigger.id}",
            publisher=publisher or get_job_publisher(),
        ),
    )


def run_agent(
    db: Session,
    llm: LLMClient,
    *,
    agent: str,
    condominium: Condominium,
    conversation: Conversation,
    trigger: Message,
    system: str,
    context: str,
    registry: ToolRegistry,
    make_context: Callable[[uuid.UUID], ToolContext],
    escalate_on_give_up: bool = True,
    give_up_reply: str = GAVE_UP_REPLY,
) -> AgentRun:
    """Run an agent for one inbound message and return the stored run, whose
    `reply_text` is what to send. Idempotent per trigger message.

    `escalate_on_give_up` hands the conversation to staff when the model produces no
    answer (dashboard flow). Without it, the sender gets `give_up_reply` instead."""
    existing = db.scalar(select(AgentRun).where(AgentRun.trigger_message_id == trigger.id))
    if existing is not None and existing.status != AgentRunStatus.RUNNING:
        return existing

    run = existing or AgentRun(
        condominium_id=condominium.id,
        conversation_id=conversation.id,
        trigger_message_id=trigger.id,
        agent=agent,
        model=llm.model,
        status=AgentRunStatus.RUNNING,
        tool_calls=[],
    )
    if existing is None:
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # another worker claimed this message
            return db.scalars(
                select(AgentRun).where(AgentRun.trigger_message_id == trigger.id)
            ).one()

    ctx = make_context(run.id)
    usage = Usage()
    calls: list[dict] = []
    reply: str | None = None
    status = AgentRunStatus.SUCCEEDED
    error: str | None = None

    try:
        session = llm.start(
            system=system,
            context=context,
            history=load_history(db, conversation),
            tools=registry.specs(),
        )
        for _ in range(MAX_STEPS):
            turn = session.next_turn()
            usage.add(turn.usage)
            if turn.model:
                run.model = turn.model
            if turn.stop == StopReason.REFUSAL:
                reply, error = REFUSAL_REPLY, "model refused"
                break
            if turn.tool_calls:
                outcomes = [_execute(db, registry, ctx, c, calls) for c in turn.tool_calls]
                session.add_tool_outcomes(outcomes)
                continue
            reply = turn.text or None
            if reply is None:
                error = f"empty reply (stop={turn.stop.value})"
            break
        else:
            error = "step limit reached"
    except LLMError as exc:
        logger.warning("concierge LLM failure", extra={"agent_run_id": str(run.id)})
        status, error, reply = AgentRunStatus.FAILED, str(exc), TECHNICAL_ERROR_REPLY

    if reply is None and not escalate_on_give_up:
        reply, status = give_up_reply, AgentRunStatus.FAILED
    elif reply is None:
        # The model never produced an answer: hand over rather than leave the resident hanging.
        reply = GAVE_UP_REPLY
        status = AgentRunStatus.ESCALATED
        conversations.escalate(
            db,
            condominium,
            conversation,
            reason=f"Assistente não concluiu o atendimento ({error}).",
            actor_type=ActorType.AGENT,
            actor_id=run.id,
        )
    elif conversation.status == ConversationStatus.ESCALATED:
        status = AgentRunStatus.ESCALATED

    run.status = status
    run.error = error
    run.reply_text = reply
    run.tool_calls = calls
    run.input_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    run.output_tokens = usage.output_tokens
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run


def _execute(
    db: Session, registry: ToolRegistry, ctx: ToolContext, call: ToolCall, log: list[dict]
) -> ToolOutcome:
    entry: dict = {"tool": call.name, "input": call.input}
    tool = registry.get(call.name)
    try:
        if tool is None:
            raise ToolError(f"Unknown tool: {call.name}")
        try:
            args = tool.args_model.model_validate(call.input)
        except ValidationError as exc:
            raise ToolError(f"Invalid arguments: {exc.errors(include_url=False)}") from exc
        result = tool.run(db, ctx, args)
        entry.update(result.log)
        entry.update(ok=result.ok, error=result.error)
        content = (
            json.dumps(result.data, ensure_ascii=False, sort_keys=True)
            if result.ok
            else (result.error or "failed")
        )
        return ToolOutcome(call.id, content, is_error=not result.ok)
    except ToolError as exc:
        entry.update(ok=False, error=str(exc))
        return ToolOutcome(call.id, str(exc), is_error=True)
    except Exception as exc:  # a bug in a tool must not crash the conversation
        db.rollback()
        logger.exception("tool crashed", extra={"tool": call.name})
        entry.update(ok=False, error=f"internal error: {type(exc).__name__}")
        return ToolOutcome(call.id, "Internal error; this action did not happen.", is_error=True)
    finally:
        log.append(entry)
