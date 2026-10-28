"""Deterministic LLM stand-ins: a scriptable one for tests, and a rule-based one so the
WhatsApp flow can be exercised locally without an API key."""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from app.llm.base import (
    ChatMessage,
    StopReason,
    ToolCall,
    ToolOutcome,
    ToolSpec,
    Turn,
)

_ids = itertools.count(1)


def say(text: str) -> Turn:
    return Turn(text=text, tool_calls=[], stop=StopReason.END)


def call(name: str, **args) -> Turn:
    return Turn(
        text="",
        tool_calls=[ToolCall(id=f"call_{next(_ids)}", name=name, input=args)],
        stop=StopReason.TOOL_USE,
    )


@dataclass
class ScriptedSession:
    llm: "ScriptedLLM"
    system: str
    context: str
    history: list[ChatMessage]
    tools: list[ToolSpec]
    outcomes: list[ToolOutcome] = field(default_factory=list)

    def next_turn(self) -> Turn:
        step = self.llm.script.pop(0)
        return step(self) if callable(step) else step

    def add_tool_outcomes(self, outcomes: list[ToolOutcome]) -> None:
        self.outcomes.extend(outcomes)


@dataclass
class ScriptedLLM:
    """Plays back turns in order. A step may be a callable that inspects the session
    (e.g. to answer from the last tool outcome) or raises to simulate an outage."""

    script: list[Turn | Callable[[ScriptedSession], Turn]] = field(default_factory=list)
    model: str = "scripted"
    sessions: list[ScriptedSession] = field(default_factory=list)

    def start(self, *, system, context, history, tools) -> ScriptedSession:
        session = ScriptedSession(self, system, context, history, tools)
        self.sessions.append(session)
        return session


class RuleBasedLLM:
    """Local-development responder. Recognises a few phrases and uses the real tools,
    so enrollment, escalation and the dashboard can be tried without model calls."""

    model = "rule-based-dev"

    def start(self, *, system, context, history, tools) -> "_RuleSession":
        return _RuleSession(history[-1].text.lower() if history else "")


_PROBLEM = (
    "quebr",
    "não funciona",
    "nao funciona",
    "parou",
    "vazando",
    "vazamento",
    "estragad",
    "queimad",
    "entupid",
    "chamado",
)
_EMERGENCY = (
    "gás",
    "gas ",
    "fogo",
    "incêndio",
    "incendio",
    "fumaça",
    "fumaca",
    "alag",
    "preso",
    "ferido",
)
_QUESTION = (
    "pode",
    "posso",
    "horário",
    "horario",
    "regra",
    "permitido",
    "proibido",
    "qual",
    "quando",
    "como funciona",
)


@dataclass
class _RuleSession:
    message: str
    outcomes: list[ToolOutcome] = field(default_factory=list)
    last_tool: str | None = None

    def next_turn(self) -> Turn:
        if self.outcomes:
            return say(self._answer(self.outcomes[-1]))
        m = self.message
        if any(w in m for w in ("atendente", "humano", "pessoa", "síndico")):
            return self._call("escalate_to_human", reason="Morador pediu atendimento humano.")
        if any(w in m for w in _EMERGENCY):
            return self._call(
                "create_maintenance_ticket",
                title=m[:80],
                description=m,
                location=m[:150],
                in_own_unit=False,
                category="security",
                priority="emergency",
            )
        if any(w in m for w in _PROBLEM):
            return self._call(
                "create_maintenance_ticket",
                title=m[:80],
                description=m,
                location=m[:150],
                in_own_unit=False,
                category="other",
                priority="normal",
            )
        if "meus chamados" in m or "meu chamado" in m:
            return self._call("get_my_tickets")
        if any(w in m for w in ("cadastro", "unidade", "apartamento")):
            return self._call("get_resident_context")
        if any(w in m for w in _QUESTION):
            return self._call("search_condominium_documents", query=m)
        return say(
            "Olá! Sou o assistente do condomínio (modo de desenvolvimento, sem IA). Posso "
            "responder sobre regras, abrir chamados, mostrar seu cadastro ou chamar a equipe."
        )

    def _call(self, name: str, **args) -> Turn:
        self.last_tool = name
        return call(name, **args)

    def _answer(self, outcome: ToolOutcome) -> str:
        if outcome.is_error:
            return f"(modo de desenvolvimento) Não consegui: {outcome.content}"
        data = json.loads(outcome.content)
        suffix = " (modo de desenvolvimento, sem IA)"
        if self.last_tool == "escalate_to_human":
            return "Encaminhei sua mensagem para a equipe. Em breve alguém responde aqui."
        if self.last_tool == "search_condominium_documents":
            if not data["results"]:
                return "Não encontrei isso nos documentos do condomínio." + suffix
            top = data["results"][0]
            return f"{top['excerpt'][:400]} (Fonte: {top['source']})" + suffix
        if self.last_tool == "create_maintenance_ticket":
            text = f"Chamado {data['reference']} registrado ({data['priority']})."
            if data["emergency_procedure_started"]:
                text = "Ligue para 193 se houver risco. " + text + " O plantão foi alertado."
            return text + suffix
        if self.last_tool == "get_my_tickets":
            items = [f"{t['reference']} {t['title']}: {t['status']}" for t in data["tickets"]]
            return ("; ".join(items) or "Você não tem chamados.") + suffix
        units = ", ".join(f"{u['unit']} ({u['relationship']})" for u in data["units"])
        return (
            f"{data['first_name']}, no {data['condominium']} seu cadastro está em: "
            f"{units or 'nenhuma unidade'}." + suffix
        )

    def add_tool_outcomes(self, outcomes: list[ToolOutcome]) -> None:
        self.outcomes.extend(outcomes)
