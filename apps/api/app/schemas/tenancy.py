import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.rbac.permissions import Role
from app.schemas.common import ORMModel


class CondominiumBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, pattern=r"^\d{5}-?\d{3}$")
    timezone: str = "America/Sao_Paulo"
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=20)


class CondominiumCreate(CondominiumBase):
    pass


class CondominiumUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, pattern=r"^\d{5}-?\d{3}$")
    timezone: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=20)


class CondominiumOut(ORMModel, CondominiumBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    whatsapp_phone_number_id: str | None
    manager_phone_e164: str | None = None
    manager_phone_requested_at: datetime | None = None
    manager_phone_confirmed_at: datetime | None = None
    created_at: datetime


class WhatsAppConfig(BaseModel):
    whatsapp_phone_number_id: str | None = Field(default=None, pattern=r"^\d{6,30}$")


class ManagerPhoneConfig(BaseModel):
    # Any common Brazilian format; normalized to E.164. Null removes it.
    number: str | None = Field(default=None, max_length=30)


class CondominiumAccess(BaseModel):
    """A condominium the current user can open, with their role in it."""

    condominium: CondominiumOut
    role: Role


class BuildingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BuildingUpdate(BuildingCreate):
    pass


class BuildingOut(ORMModel):
    id: uuid.UUID
    condominium_id: uuid.UUID
    name: str


class UnitCreate(BaseModel):
    building_id: uuid.UUID | None = None
    identifier: str = Field(min_length=1, max_length=40)
    floor: str | None = Field(default=None, max_length=10)


class UnitUpdate(BaseModel):
    building_id: uuid.UUID | None = None
    identifier: str | None = Field(default=None, min_length=1, max_length=40)
    floor: str | None = Field(default=None, max_length=10)


class UnitOut(ORMModel):
    id: uuid.UUID
    condominium_id: uuid.UUID
    building_id: uuid.UUID | None
    identifier: str
    floor: str | None


class MembershipSummary(BaseModel):
    organization_id: uuid.UUID
    condominium_id: uuid.UUID
    condominium_name: str
    role: Role


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_platform_admin: bool
    condominiums: list[MembershipSummary]


class StaffInvite(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=200)
    role: str = Field(pattern="^(manager|staff)$")


class StaffMemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    has_signed_in: bool
    created_at: datetime


class CondominiumSummary(BaseModel):
    """Aggregate counts only; safe for any role that can read the condominium."""

    buildings: int
    units: int
    residents_by_status: dict[str, int]
    staff: int
    conversations_escalated: int
    tickets_open: int
    tickets_emergency_open: int
    documents_failed: int
