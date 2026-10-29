"""The WhatsApp agent for sheet-backed condominiums (ADR 0010/0011): one run per inbound
message from a person found in the Pessoas sheet. Its tools depend on their role."""

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agents.concierge import run_agent
from app.agents.delivery_tools import (
    CloseDelivery,
    FindDeliveries,
    GetMyDeliveries,
    RecordDelivery,
)
from app.agents.occurrence_tools import (
    FindOccurrences,
    GetMyOccurrences,
    ReportOccurrence,
    UpdateOccurrence,
)
from app.agents.people_tools import FindPeople, GetMyRegistration, RegisterPerson, UpdatePerson
from app.agents.rule_tools import ListDocuments, RemoveDocument, SearchRules
from app.agents.tools import ToolContext, ToolRegistry
from app.agents.visitor_tools import (
    AnnounceVisitor,
    AnswerVisitor,
    AuthorizeVisitor,
    CancelVisitor,
    CheckVisitor,
    GetMyVisitors,
    RecordVisitorEntry,
)
from app.core.jobs import JobPublisher, get_job_publisher
from app.integrations.google.base import Google
from app.llm.base import LLMClient
from app.models import AgentRun, Condominium, Conversation, Message
from app.services.people import ROLE_LABEL, Person, PersonRole

# Static so the provider can cache it; per-run facts go in render_context.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "zela_system.md").read_text(encoding="utf-8")

GAVE_UP_REPLY = (
    "Desculpe, não consegui concluir seu pedido agora. Pode tentar de novo com outras "
    "palavras? Se for urgente, fale direto com o síndico."
)


def build_registry(role: PersonRole) -> ToolRegistry:
    """The sender's tools, decided by the role the backend identified (ADR 0011).
    Order is fixed per role, which keeps each role's cached prompt prefix stable."""
    registry = ToolRegistry()
    registry.register(GetMyRegistration())
    registry.register(ReportOccurrence())
    registry.register(GetMyOccurrences())
    registry.register(GetMyDeliveries())
    registry.register(SearchRules())
    if role != PersonRole.STAFF:
        registry.register(AuthorizeVisitor())
        registry.register(GetMyVisitors())
        registry.register(AnswerVisitor())
        registry.register(CancelVisitor())
    if role in (PersonRole.STAFF, PersonRole.MANAGER):
        registry.register(RecordDelivery())
        registry.register(FindDeliveries())
        registry.register(CloseDelivery())
        registry.register(CheckVisitor())
        registry.register(AnnounceVisitor())
        registry.register(RecordVisitorEntry())
    if role == PersonRole.MANAGER:
        registry.register(RegisterPerson())
        registry.register(FindPeople())
        registry.register(UpdatePerson())
        registry.register(FindOccurrences())
        registry.register(UpdateOccurrence())
        registry.register(ListDocuments())
        registry.register(RemoveDocument())
    return registry


def render_context(condominium: Condominium, person: Person, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(condominium.timezone))
    units = ", ".join(f"{m.label} ({ROLE_LABEL[m.role]})" for m in person.memberships) or "nenhuma"
    return (
        f"Condomínio: {condominium.name}\n"
        f"Quem está escrevendo: {person.first_name or '(sem nome no cadastro)'}\n"
        f"Papel: {person.role_label}\n"
        f"Unidades no cadastro: {units}\n"
        f"Data e hora local: {local:%d/%m/%Y %H:%M}"
    )


def run_zela(
    db: Session,
    llm: LLMClient,
    *,
    condominium: Condominium,
    conversation: Conversation,
    person: Person,
    trigger: Message,
    google: Google,
    publisher: JobPublisher | None = None,
) -> AgentRun:
    return run_agent(
        db,
        llm,
        agent="zela",
        condominium=condominium,
        conversation=conversation,
        trigger=trigger,
        system=SYSTEM_PROMPT,
        context=render_context(condominium, person, datetime.now(timezone.utc)),
        registry=build_registry(person.role),
        make_context=lambda run_id: ToolContext(
            condominium_id=condominium.id,
            conversation_id=conversation.id,
            agent_run_id=run_id,
            idempotency_key=f"msg:{trigger.id}",
            publisher=publisher or get_job_publisher(),
            person=person,
            google=google,
        ),
        # No dashboard to hand over to: answer instead of going silent.
        escalate_on_give_up=False,
        give_up_reply=GAVE_UP_REPLY,
    )
