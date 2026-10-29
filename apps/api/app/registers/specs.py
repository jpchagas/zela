"""The spreadsheets Zela keeps for each condominium, and their columns.

Columns are matched by header text (accents, case and spacing ignored), so the manager
may reorder them or add their own. Adding a column here is safe: missing headers are
appended to existing sheets the next time Zela opens them. Renaming a header is not:
the old column would stop matching.
"""

from dataclasses import dataclass

from app.models.enums import RegisterKind


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegisterSpec:
    kind: RegisterKind
    title: str  # file name and tab title, e.g. "Pessoas"
    columns: tuple[Column, ...]

    @property
    def headers(self) -> list[str]:
        return [c.header for c in self.columns]

    @property
    def choices(self) -> dict[int, list[str]]:
        return {i: list(c.choices) for i, c in enumerate(self.columns) if c.choices}

    def column(self, key: str) -> Column:
        for c in self.columns:
            if c.key == key:
                return c
        raise KeyError(key)


# First column of every register: lets Zela find its own rows and skip duplicate writes.
ID = Column("zela_id", "ID Zela")

PEOPLE = RegisterSpec(
    RegisterKind.PEOPLE,
    "Pessoas",
    (
        ID,
        Column("name", "Nome"),
        Column("whatsapp", "WhatsApp"),
        Column("block", "Bloco"),
        Column("unit", "Unidade"),
        Column("role", "Papel", ("Síndico", "Proprietário", "Morador", "Funcionário")),
        Column("status", "Situação", ("Ativo", "Inativo")),
        Column("notes", "Observações"),
        Column("created_at", "Cadastrado em"),
        Column("updated_at", "Atualizado em"),
    ),
)

OCCURRENCES = RegisterSpec(
    RegisterKind.OCCURRENCES,
    "Ocorrências",
    (
        ID,
        Column("number", "Número"),
        Column("opened_at", "Aberta em"),
        Column("type", "Tipo", ("Manutenção", "Reclamação", "Sugestão", "Outro")),
        Column("description", "Descrição"),
        Column("location", "Local"),
        Column("block", "Bloco"),
        Column("unit", "Unidade"),
        Column(
            "category",
            "Categoria",
            (
                "Elevadores",
                "Portões e acesso",
                "Hidráulica",
                "Elétrica",
                "Limpeza",
                "Segurança",
                "Áreas comuns",
                "Barulho e convivência",
                "Outros",
            ),
        ),
        Column("priority", "Prioridade", ("Baixa", "Normal", "Alta", "Emergência")),
        # Kept apart from the confirmed values above (AI suggestions are never records).
        Column("ai_suggestion", "Sugestão da IA"),
        Column(
            "status",
            "Status",
            ("Aberta", "Em andamento", "Aguardando", "Resolvida", "Cancelada"),
        ),
        Column("reported_by", "Registrada por"),
        Column("reported_by_id", "ID de quem registrou"),
        Column("assignee", "Responsável"),
        Column("notes", "Observações"),
        Column("updated_at", "Atualizada em"),
        Column("closed_at", "Encerrada em"),
    ),
)

VISITORS = RegisterSpec(
    RegisterKind.VISITORS,
    "Visitantes",
    (
        ID,
        Column("code", "Código"),
        Column("visitor", "Visitante"),
        Column("block", "Bloco"),
        Column("unit", "Unidade"),
        Column("authorized_by", "Autorizado por"),
        Column("authorized_by_id", "ID de quem autorizou"),
        Column("visit_date", "Data da visita"),
        Column("valid_until", "Válido até"),
        Column(
            "status",
            "Status",
            (
                "Autorizado",
                "Aguardando morador",
                "Entrou",
                "Recusado",
                "Cancelado",
                "Expirado",
            ),
        ),
        Column("entered_at", "Entrada em"),
        Column("checked_by", "Conferido por"),
        Column("notes", "Observações"),
        # Who at the desk announced or let the visitor in, to tell them the unit's answer.
        Column("checked_by_id", "ID de quem conferiu"),
    ),
)

DELIVERIES = RegisterSpec(
    RegisterKind.DELIVERIES,
    "Encomendas",
    (
        ID,
        Column("number", "Número"),
        Column("received_at", "Recebida em"),
        Column("block", "Bloco"),
        Column("unit", "Unidade"),
        Column("recipient", "Destinatário"),
        Column("description", "Descrição"),
        Column("received_by", "Recebida por"),
        Column("status", "Status", ("Aguardando retirada", "Retirada", "Devolvida")),
        Column("notified_at", "Morador avisado em"),
        Column("picked_up_at", "Retirada em"),
        Column("picked_up_by", "Retirada por"),
        Column("notes", "Observações"),
    ),
)

REGISTERS: dict[RegisterKind, RegisterSpec] = {
    spec.kind: spec for spec in (PEOPLE, OCCURRENCES, VISITORS, DELIVERIES)
}
