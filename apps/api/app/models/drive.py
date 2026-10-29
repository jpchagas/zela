import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import DriveStatus, RegisterKind, RegisterStatus, db_enum


class DriveConnection(IdMixin, TimestampMixin, Base):
    """The manager's Google Drive grant for one condominium. The condominium's records
    live in that Drive; this row only holds what Zela needs to reach them."""

    __tablename__ = "drive_connections"
    __table_args__ = (UniqueConstraint("condominium_id", "id"),)

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="google")
    account_email: Mapped[str] = mapped_column(String(320))
    # Fernet ciphertext (app.core.crypto). Never log or return it.
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(String(500))
    folder_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[DriveStatus] = mapped_column(db_enum(DriveStatus), default=DriveStatus.ACTIVE)
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SheetRegister(IdMixin, TimestampMixin, Base):
    """Where one register (Pessoas, Ocorrências...) lives. Deleted with its connection;
    the spreadsheet itself stays in the manager's Drive."""

    __tablename__ = "sheet_registers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "connection_id"],
            ["drive_connections.condominium_id", "drive_connections.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("condominium_id", "kind"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[RegisterKind] = mapped_column(db_enum(RegisterKind))
    status: Mapped[RegisterStatus] = mapped_column(
        db_enum(RegisterStatus), default=RegisterStatus.PENDING
    )
    spreadsheet_id: Mapped[str | None] = mapped_column(String(128))
    # The tab's numeric ID, which survives the manager renaming the tab.
    sheet_id: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(300))
