import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import ResidentStatus, UnitRelationship
from app.schemas.common import ORMModel


class PhoneIn(BaseModel):
    number: str = Field(min_length=8, max_length=30, description="Any common format; BR default")
    is_primary: bool = False


class PhoneOut(ORMModel):
    id: uuid.UUID
    phone_e164: str
    is_primary: bool
    verified_at: datetime | None


class UnitMembershipIn(BaseModel):
    unit_id: uuid.UUID
    relationship: UnitRelationship


class UnitMembershipOut(ORMModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    relationship: UnitRelationship
    started_at: datetime
    ended_at: datetime | None


class ResidentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phones: list[PhoneIn] = Field(default_factory=list, max_length=5)
    units: list[UnitMembershipIn] = Field(default_factory=list, max_length=10)


class ResidentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None


class ResidentStatusChange(BaseModel):
    status: ResidentStatus


class ResidentOut(ORMModel):
    id: uuid.UUID
    condominium_id: uuid.UUID
    full_name: str
    email: str | None
    status: ResidentStatus
    status_changed_at: datetime
    created_at: datetime


class ResidentDetail(ResidentOut):
    phones: list[PhoneOut]
    units: list[UnitMembershipOut]
