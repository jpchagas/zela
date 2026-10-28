import enum

from sqlalchemy import Enum as SAEnum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        return self.value


def db_enum(enum_cls: type[enum.Enum], name: str | None = None) -> SAEnum:
    """Store enums as VARCHAR + CHECK so adding a value is a plain migration, not ALTER TYPE.

    `name` names the CHECK constraint; pass it when a table has two columns of the same enum.
    """
    return SAEnum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class OrgRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"


class StaffRole(StrEnum):
    MANAGER = "manager"
    STAFF = "staff"


class ResidentStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class UnitRelationship(StrEnum):
    OWNER = "owner"
    TENANT = "tenant"
    AUTHORIZED_OCCUPANT = "authorized_occupant"


class ActorType(StrEnum):
    USER = "user"
    RESIDENT = "resident"
    AGENT = "agent"
    SYSTEM = "system"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ESCALATED = "escalated"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageKind(StrEnum):
    """Lets the UI and the resident tell AI replies apart from staff and system messages."""

    RESIDENT = "resident"
    AI_REPLY = "ai_reply"
    # Fixed automated replies (enrollment prompts, unsupported media). Not model output.
    SYSTEM_REPLY = "system_reply"
    STAFF_REPLY = "staff_reply"
    NOTIFICATION = "notification"
    ANNOUNCEMENT = "announcement"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    # Notification no longer true when its turn came (e.g. the ticket moved on).
    SKIPPED = "skipped"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_INFORMATION = "waiting_information"
    WAITING_EXTERNAL = "waiting_external"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketCategory(StrEnum):
    """Fixed list (one for every condominium for now). The AI may only suggest these."""

    ELEVATORS = "elevators"
    GATES_ACCESS = "gates_access"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CLEANING = "cleaning"
    SECURITY = "security"
    COMMON_AREAS = "common_areas"
    NOISE = "noise"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class VisitorAuthorizationStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    USED = "used"
    EXPIRED = "expired"


class DocumentVisibility(StrEnum):
    RESIDENTS = "residents"
    STAFF = "staff"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    INACTIVE = "inactive"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ESCALATED = "escalated"


class JobStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
