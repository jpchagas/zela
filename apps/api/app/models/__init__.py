"""Import every model so Base.metadata is complete for Alembic and tests."""

from app.models.audit import AgentRun, AuditEvent
from app.models.drive import DriveConnection, SheetRegister
from app.models.identity import OrganizationMembership, StaffMembership, User
from app.models.knowledge import Document, DocumentChunk
from app.models.messaging import Conversation, Message, NotificationEvent, WebhookEvent
from app.models.operations import (
    CondominiumCounter,
    MaintenanceTicket,
    TicketEvent,
    VisitorAuthorization,
)
from app.models.residents import EnrollmentCode, Resident, ResidentPhone, UnitMembership
from app.models.tenancy import Building, Condominium, EmergencyContact, Organization, Unit

__all__ = [
    "AgentRun",
    "AuditEvent",
    "Building",
    "Condominium",
    "CondominiumCounter",
    "Conversation",
    "Document",
    "EnrollmentCode",
    "DocumentChunk",
    "DriveConnection",
    "EmergencyContact",
    "MaintenanceTicket",
    "Message",
    "NotificationEvent",
    "Organization",
    "OrganizationMembership",
    "Resident",
    "ResidentPhone",
    "SheetRegister",
    "StaffMembership",
    "TicketEvent",
    "Unit",
    "UnitMembership",
    "User",
    "VisitorAuthorization",
    "WebhookEvent",
]
