"""The manager's own WhatsApp number (ADR 0011).

Set on the setup page, then confirmed from the phone itself: Zela sends a template and
the manager answers SIM. Only a confirmed number counts as the manager, so a typo on
the setup page can't hand someone else the right to register people.
"""

import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden
from app.core.jobs import JobPublisher
from app.integrations.whatsapp.templates import MANAGER_CONFIRMATION
from app.models import Condominium
from app.models.enums import ActorType
from app.rbac.context import CondoContext
from app.services import audit, notifications
from app.services.phones import normalize_phone

CONFIRMATION_TTL = timedelta(days=7)
YES = {"sim", "s", "confirmo", "sim confirmo", "confirmar", "sou eu", "sim sou eu"}

ASK_YES = (
    "Para confirmar que este é o WhatsApp do síndico do {condo} no Zela, responda SIM. "
    "Se não reconhece este pedido, ignore esta mensagem."
)
EXPIRED = (
    "O pedido de confirmação deste número expirou. Informe o número de novo na página de "
    "configuração do Zela para receber outra mensagem."
)
CONFIRMED = (
    "Pronto! Este é agora o WhatsApp do síndico do {condo} no Zela. Por aqui você pode "
    'cadastrar pessoas (por exemplo: "cadastrar Maria Souza, apto 302, 11 98765-4321, '
    'moradora"), procurar e corrigir cadastros.'
)
CONFIRMED_NO_DRIVE = " Antes, conecte o Google Drive na página de configuração."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def set_manager_phone(
    db: Session, ctx: CondoContext, number: str | None, publisher: JobPublisher
) -> Condominium:
    if not ctx.is_org_level:
        raise Forbidden("Only organization admins can set the manager's WhatsApp")
    condo = ctx.condominium
    if not (number or "").strip():
        condo.manager_phone_e164 = None
        condo.manager_phone_requested_at = None
        condo.manager_phone_confirmed_at = None
        audit.record_user_action(
            db, ctx, "condominium.manager_phone_removed", "condominium", condo.id
        )
        db.commit()
        return condo

    e164 = normalize_phone(number)
    if not condo.whatsapp_phone_number_id:
        raise Conflict("Connect the condominium's WhatsApp number first")
    if e164 == condo.manager_phone_e164 and condo.manager_phone_confirmed_at:
        return condo
    condo.manager_phone_e164 = e164
    condo.manager_phone_requested_at = _now()
    condo.manager_phone_confirmed_at = None
    audit.record_user_action(db, ctx, "condominium.manager_phone_set", "condominium", condo.id)
    db.commit()
    notifications.enqueue(
        db,
        publisher,
        condominium_id=condo.id,
        recipient_e164=e164,
        template=MANAGER_CONFIRMATION.name,
        params={"condominium": condo.name},
        # A new request (or a resend) is a new message; a retried job is not.
        idempotency_key=f"manager-confirm:{condo.id}:{condo.manager_phone_requested_at.isoformat()}",
        entity_type="condominium",
        entity_id=condo.id,
        guard={"manager_phone_pending": e164},
    )
    return condo


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    letters = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in decomposed)
    return " ".join("".join(ch for ch in letters if not unicodedata.combining(ch)).split())


def handle_inbound(
    db: Session, condo: Condominium, contact: str, text: str | None, *, drive_connected: bool
) -> str | None:
    """The reply when this message belongs to a pending confirmation, else None."""
    if condo.manager_phone_e164 != contact or condo.manager_phone_confirmed_at is not None:
        return None
    requested = condo.manager_phone_requested_at
    if requested is None or _now() - requested > CONFIRMATION_TTL:
        return EXPIRED
    if text is None or _normalize(text) not in YES:
        return ASK_YES.format(condo=condo.name)
    condo.manager_phone_confirmed_at = _now()
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="condominium.manager_phone_confirmed",
        entity_type="condominium",
        entity_id=condo.id,
    )
    db.commit()
    reply = CONFIRMED.format(condo=condo.name)
    return reply if drive_connected else reply + CONFIRMED_NO_DRIVE
