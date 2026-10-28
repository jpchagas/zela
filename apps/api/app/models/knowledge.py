import uuid
from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import DocumentStatus, DocumentVisibility, db_enum


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_condo_status", "condominium_id", "status"),
        UniqueConstraint("condominium_id", "id"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    storage_uri: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    visibility: Mapped[DocumentVisibility] = mapped_column(
        db_enum(DocumentVisibility), default=DocumentVisibility.RESIDENTS
    )
    status: Mapped[DocumentStatus] = mapped_column(
        db_enum(DocumentStatus), default=DocumentStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    # Set on an upload that replaces another document; the old one is deactivated only
    # once this one indexes successfully.
    replaces_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    size_bytes: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class DocumentChunk(IdMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "document_id"],
            ["documents.condominium_id", "documents.id"],
            ondelete="CASCADE",
        ),
        Index("ix_document_chunks_search", "search_vector", postgresql_using="gin"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(index=True)
    ordinal: Mapped[int] = mapped_column()
    page: Mapped[int | None] = mapped_column()
    heading: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        # pt_unaccent = Portuguese stemming + unaccent, so "horario" matches "horário".
        Computed(
            "to_tsvector('pt_unaccent'::regconfig, coalesce(heading, '') || ' ' || content)",
            persisted=True,
        ),
    )
