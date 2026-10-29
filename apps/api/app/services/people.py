"""People of a condominium, as recorded in its Pessoas sheet (ADR 0011).

Who is writing on WhatsApp, and what they may do, is decided here from the stored
record: the manager's confirmed number (Postgres) and the sender's rows in Pessoas.
Rows a person typed by hand are validated like any other input; a row with an
unreadable number or role grants nothing.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import InvalidInput
from app.integrations.google.base import Google
from app.models import Condominium
from app.models.enums import RegisterKind, StrEnum
from app.registers.table import Row, Table, normalize_header
from app.services import drive
from app.services.phones import normalize_phone


class PersonRole(StrEnum):
    MANAGER = "manager"
    STAFF = "staff"
    OWNER = "owner"
    RESIDENT = "resident"


# Sheet values, as the manager sees them in the Papel dropdown.
ROLE_LABEL = {
    PersonRole.MANAGER: "Síndico",
    PersonRole.OWNER: "Proprietário",
    PersonRole.RESIDENT: "Morador",
    PersonRole.STAFF: "Funcionário",
}
# When one number has rows with different roles, the broadest one applies.
_PRECEDENCE = [PersonRole.MANAGER, PersonRole.STAFF, PersonRole.OWNER, PersonRole.RESIDENT]
# Normalized prefixes, so "síndica", "Moradora", "inquilino" or "porteiro" all read.
_ROLE_PREFIXES = (
    ("sindic", PersonRole.MANAGER),
    ("propriet", PersonRole.OWNER),
    ("morador", PersonRole.RESIDENT),
    ("inquilin", PersonRole.RESIDENT),
    ("funcion", PersonRole.STAFF),
    ("porteir", PersonRole.STAFF),
    ("zelador", PersonRole.STAFF),
)
STATUS_ACTIVE = "Ativo"
STATUS_INACTIVE = "Inativo"


@dataclass(frozen=True)
class Membership:
    zela_id: str
    block: str
    unit: str
    role: PersonRole

    @property
    def label(self) -> str:
        return " ".join(p for p in (self.block, self.unit) if p) or "-"


@dataclass(frozen=True)
class Person:
    """The identified sender. `memberships` are their own rows only."""

    phone: str
    name: str
    role: PersonRole
    memberships: tuple[Membership, ...]
    # Set when the sender is the confirmed manager number from setup.
    is_confirmed_manager: bool = False

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else ""

    @property
    def role_label(self) -> str:
        return ROLE_LABEL[self.role]


def parse_role(text: str) -> PersonRole | None:
    value = normalize_header(text)
    for prefix, role in _ROLE_PREFIXES:
        if value.startswith(prefix):
            return role
    return None


def is_active(row: Row) -> bool:
    return not normalize_header(row.values.get("status", "")).startswith("inativ")


def phone_of(row: Row) -> str | None:
    raw = row.values.get("whatsapp", "")
    if not raw.strip():
        return None
    try:
        return normalize_phone(raw)
    except InvalidInput:
        return None


def identify(db: Session, google: Google, condo: Condominium, contact: str) -> Person | None:
    """Raises drive.RegisterUnavailable when the Pessoas sheet can't be read."""
    confirmed_manager = bool(
        condo.manager_phone_confirmed_at and condo.manager_phone_e164 == contact
    )
    table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    rows = [r for r in table.rows if phone_of(r) == contact and is_active(r)]
    memberships = [
        Membership(r.zela_id, r.values["block"], r.values["unit"], role)
        for r in rows
        if (role := parse_role(r.values["role"])) is not None
    ]
    if not memberships and not confirmed_manager:
        return None
    roles = {m.role for m in memberships}
    if confirmed_manager:
        roles.add(PersonRole.MANAGER)
    name = next((r.values["name"] for r in rows if r.values["name"]), "")
    return Person(
        phone=contact,
        name=name,
        role=next(role for role in _PRECEDENCE if role in roles),
        memberships=tuple(memberships),
        is_confirmed_manager=confirmed_manager,
    )


def open_people(db: Session, google: Google, condominium_id: uuid.UUID) -> Table:
    """The Pessoas table, locked for writing (commit to release)."""
    return drive.open_table(db, google, condominium_id, RegisterKind.PEOPLE)


def same_place(row: Row, block: str, unit: str) -> bool:
    return normalize_header(row.values["block"]) == normalize_header(block) and normalize_header(
        row.values["unit"]
    ) == normalize_header(unit)


def new_person_id(seed: str) -> str:
    return "P-" + hashlib.sha256(seed.encode()).hexdigest()[:10].upper()


def local_timestamp(condo: Condominium, now: datetime | None = None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(condo.timezone))
    return f"{moment:%d/%m/%Y %H:%M}"


def search(table: Table, query: str, limit: int = 10) -> list[Row]:
    """Rows matching a name, unit or phone fragment, active ones first."""
    q = normalize_header(query)
    digits = "".join(ch for ch in query if ch.isdigit())
    matches = []
    for row in table.rows:
        haystack = normalize_header(" ".join(row.values[k] for k in ("name", "block", "unit")))
        row_digits = "".join(ch for ch in row.values["whatsapp"] if ch.isdigit())
        if (q and q in haystack) or (len(digits) >= 4 and digits in row_digits):
            matches.append(row)
    matches.sort(key=lambda r: not is_active(r))
    return matches[:limit]
