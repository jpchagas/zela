"""Resident enrollment on WhatsApp (PDD Journey A).

A manager issues a one-time code for one registered phone. The resident sends it from that
phone. Enrollment succeeds only when the sender number and the code both match, so a
leaked code is useless from another number and a matching number is useless without it.
"""

import enum
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict
from app.models import Condominium, EnrollmentCode, Resident, ResidentPhone
from app.models.enums import ActorType, ResidentStatus
from app.rbac.context import CondoContext
from app.services import audit
from app.services.common import get_scoped

# No 0/O or 1/I, so codes survive being read aloud or copied by hand.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL = timedelta(days=7)
MAX_FAILED_ATTEMPTS = 5
_CODE_PATTERN = re.compile(r"\b([A-Z0-9]{4})[\s-]?([A-Z0-9]{4})\b")


class EnrollmentResult(enum.Enum):
    ENROLLED = "enrolled"
    NOT_A_CODE = "not_a_code"
    NO_PENDING_CODE = "no_pending_code"
    WRONG_CODE = "wrong_code"
    EXPIRED = "expired"
    LOCKED = "locked"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(phone_id: uuid.UUID, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{phone_id}:{code}".encode(), hashlib.sha256).hexdigest()


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def extract_code(text: str) -> str | None:
    match = _CODE_PATTERN.search(text.upper())
    return match.group(1) + match.group(2) if match else None


def issue_code(
    db: Session, ctx: CondoContext, resident_id: uuid.UUID, phone_id: uuid.UUID
) -> tuple[str, datetime]:
    """Create a code for one phone, revoking any earlier pending code for it. The plain
    code is returned once and never stored."""
    resident = get_scoped(db, Resident, ctx, resident_id)
    phone = get_scoped(db, ResidentPhone, ctx, phone_id)
    if phone.resident_id != resident.id:
        raise Conflict("Phone does not belong to this resident")
    if resident.status in (ResidentStatus.SUSPENDED, ResidentStatus.REVOKED):
        raise Conflict(f"Cannot issue a code for a resident who is {resident.status}")
    if phone.verified_at is not None:
        raise Conflict("This phone is already enrolled")

    now = _now()
    db.execute(
        update(EnrollmentCode)
        .where(
            EnrollmentCode.phone_id == phone.id,
            EnrollmentCode.used_at.is_(None),
            EnrollmentCode.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    expires_at = now + CODE_TTL
    db.add(
        EnrollmentCode(
            condominium_id=ctx.condominium_id,
            resident_id=resident.id,
            phone_id=phone.id,
            code_hash=_hash(phone.id, code),
            expires_at=expires_at,
            created_by_user_id=ctx.user.id,
        )
    )
    audit.record_user_action(
        db, ctx, "resident.enrollment_code_issued", "resident", resident.id, phone_id=str(phone.id)
    )
    db.commit()
    return format_code(code), expires_at


def find_phone(db: Session, condominium_id: uuid.UUID, e164: str) -> ResidentPhone | None:
    return db.scalar(
        select(ResidentPhone).where(
            ResidentPhone.condominium_id == condominium_id, ResidentPhone.phone_e164 == e164
        )
    )


def try_enroll(
    db: Session, condominium: Condominium, phone: ResidentPhone, text: str
) -> EnrollmentResult:
    pending = db.scalar(
        select(EnrollmentCode)
        .where(
            EnrollmentCode.phone_id == phone.id,
            EnrollmentCode.used_at.is_(None),
            EnrollmentCode.revoked_at.is_(None),
        )
        .with_for_update()
    )
    candidate = extract_code(text)
    if pending is None:
        return EnrollmentResult.NO_PENDING_CODE
    if candidate is None:
        return EnrollmentResult.NOT_A_CODE

    now = _now()
    if pending.failed_attempts >= MAX_FAILED_ATTEMPTS:
        return EnrollmentResult.LOCKED
    if pending.expires_at <= now:
        return EnrollmentResult.EXPIRED
    if not hmac.compare_digest(pending.code_hash, _hash(phone.id, candidate)):
        pending.failed_attempts += 1
        db.commit()
        if pending.failed_attempts >= MAX_FAILED_ATTEMPTS:
            return EnrollmentResult.LOCKED
        return EnrollmentResult.WRONG_CODE

    resident = db.get(Resident, phone.resident_id)
    pending.used_at = now
    phone.verified_at = now
    if resident.status == ResidentStatus.INVITED:
        resident.status = ResidentStatus.ACTIVE
        resident.status_changed_at = now
    audit.record(
        db,
        organization_id=condominium.organization_id,
        condominium_id=condominium.id,
        actor_type=ActorType.RESIDENT,
        actor_id=resident.id,
        action="resident.enrolled",
        entity_type="resident",
        entity_id=resident.id,
        data={"phone_id": str(phone.id)},
    )
    db.commit()
    return EnrollmentResult.ENROLLED
