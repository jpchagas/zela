"""Message templates for notifications sent outside WhatsApp's 24-hour window.

Each must be registered (and approved) in Meta's WhatsApp Manager with exactly this name,
language and body; see docs/whatsapp-templates.md. Inside the window the same text is
sent as a plain message, so residents always read the same wording.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    name: str
    language: str
    category: str
    body: str  # Meta placeholder syntax: {{1}}, {{2}}, ...
    params: tuple[str, ...]  # names of {{1}}..{{n}}, in order

    def values(self, params: dict[str, str]) -> list[str]:
        return [_clean(params[name]) for name in self.params]

    def render(self, params: dict[str, str]) -> str:
        text = self.body
        for i, value in enumerate(self.values(params), start=1):
            text = text.replace(f"{{{{{i}}}}}", value)
        return text


def _clean(value: str) -> str:
    # Meta rejects parameters with newlines, tabs or more than four consecutive spaces.
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value[:900] or "-"


TICKET_UPDATE = Template(
    name="zela_ticket_update",
    language="pt_BR",
    category="UTILITY",
    body="Atualização do seu chamado #{{1}} ({{2}}): {{3}}",
    params=("number", "title", "update"),
)

EMERGENCY_ALERT = Template(
    name="zela_emergency_alert",
    language="pt_BR",
    category="UTILITY",
    body=(
        "🚨 Emergência no {{1}}: {{2}}. Local: {{3}}. Chamado #{{4}}, aberto às {{5}}. "
        "O morador foi orientado a acionar o serviço de emergência. Acompanhe no painel do Zela."
    ),
    params=("condominium", "summary", "location", "number", "time"),
)

MANAGER_CONFIRMATION = Template(
    name="zela_manager_confirmation",
    language="pt_BR",
    category="UTILITY",
    body=(
        "Olá! Este número foi informado como WhatsApp do síndico do {{1}} no Zela. Se for "
        "você, responda SIM. Se não reconhece este pedido, ignore esta mensagem."
    ),
    params=("condominium",),
)

PERSON_WELCOME = Template(
    name="zela_person_welcome",
    language="pt_BR",
    category="UTILITY",
    body=(
        "Olá, {{1}}! Você foi cadastrado(a) no Zela, o atendimento do {{2}} pelo WhatsApp. "
        "É só mandar mensagem neste número quando precisar."
    ),
    params=("first_name", "condominium"),
)

OCCURRENCE_UPDATE = Template(
    name="zela_occurrence_update",
    language="pt_BR",
    category="UTILITY",
    body="Atualização da sua ocorrência #{{1}} ({{2}}): {{3}}",
    params=("number", "summary", "update"),
)

OCCURRENCE_EMERGENCY = Template(
    name="zela_occurrence_emergency",
    language="pt_BR",
    category="UTILITY",
    body=(
        "🚨 Emergência no {{1}}: {{2}}. Local: {{3}}. Ocorrência #{{4}}, registrada às {{5}} "
        "por {{6}}. A pessoa foi orientada a acionar o serviço de emergência (193, 192 ou 190)."
    ),
    params=("condominium", "summary", "location", "number", "time", "reporter"),
)

DELIVERY_ARRIVED = Template(
    name="zela_delivery_arrived",
    language="pt_BR",
    category="UTILITY",
    body=(
        "📦 Olá, {{1}}! Chegou uma encomenda para a unidade {{2}}: {{3}}. Ela está na "
        "portaria, com o número #{{4}}."
    ),
    params=("first_name", "place", "description", "number"),
)

VISITOR_AT_GATE = Template(
    name="zela_visitor_at_gate",
    language="pt_BR",
    category="UTILITY",
    body=(
        "🔔 {{1}} está na portaria do {{2}} procurando a unidade {{3}}. Pode entrar? "
        "Responda aqui com SIM ou NÃO (código {{4}})."
    ),
    params=("visitor", "condominium", "place", "code"),
)

VISITOR_ANSWER = Template(
    name="zela_visitor_answer",
    language="pt_BR",
    category="UTILITY",
    body="Portaria: a unidade {{1}} {{2}} a entrada de {{3}} (código {{4}}).",
    params=("place", "answer", "visitor", "code"),
)

VISITOR_ARRIVED = Template(
    name="zela_visitor_arrived",
    language="pt_BR",
    category="UTILITY",
    body="🔔 {{1}} entrou no {{2}} às {{3}}, com a autorização {{4}}.",
    params=("visitor", "condominium", "time", "code"),
)

TEMPLATES = {
    t.name: t
    for t in (
        TICKET_UPDATE,
        EMERGENCY_ALERT,
        MANAGER_CONFIRMATION,
        PERSON_WELCOME,
        OCCURRENCE_UPDATE,
        OCCURRENCE_EMERGENCY,
        DELIVERY_ARRIVED,
        VISITOR_AT_GATE,
        VISITOR_ANSWER,
        VISITOR_ARRIVED,
    )
}
