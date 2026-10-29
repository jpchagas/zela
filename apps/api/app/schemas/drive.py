from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DriveStatus, RegisterKind, RegisterStatus


class RegisterOut(BaseModel):
    kind: RegisterKind
    title: str
    status: RegisterStatus
    url: str | None = None
    last_error: str | None = None


class DriveStatusOut(BaseModel):
    # False when the server has no Google OAuth client configured.
    configured: bool
    connected: bool
    status: DriveStatus | None = None
    account_email: str | None = None
    connected_at: datetime | None = None
    folder_url: str | None = None
    registers: list[RegisterOut] = []


class DriveConnectOut(BaseModel):
    authorization_url: str
