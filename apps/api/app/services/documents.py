"""Condominium knowledge base: upload, background indexing, and cited search (ADR 0006).

Documents are untrusted input. Their text is only ever handed to the model as quoted
reference material, never as instructions.
"""

import hashlib
import io
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, InvalidInput
from app.integrations.storage import BlobStore
from app.models import Document, DocumentChunk
from app.models.enums import DocumentStatus, DocumentVisibility
from app.rbac.context import CondoContext
from app.services import audit
from app.services.common import get_scoped

ALLOWED_TYPES = {"application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md"}
CHUNK_TARGET = 1200  # characters; a few paragraphs, small enough to quote
CHUNK_MAX = 2000
MIN_SECTION_CHUNK = 200  # a new section starts a new chunk unless the current one is tiny
# Lines that open a section in regulations and minutes ("CAPÍTULO III", "Seção 2").
# Articles are not headings: chunk text keeps "Art. 12", which the model can cite.
_HEADING = re.compile(r"^\s*(cap[ií]tulo|se[cç][aã]o|t[ií]tulo)\b", re.IGNORECASE)


_PT_CONFIG = literal_column("'pt_unaccent'::regconfig")


class ExtractionError(Exception):
    """The file could not be turned into searchable text."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Upload and lifecycle -----------------------------------------------------------------


def upload(
    db: Session,
    ctx: CondoContext,
    store: BlobStore,
    *,
    title: str,
    filename: str,
    content_type: str,
    data: bytes,
    visibility: DocumentVisibility,
    replaces_document_id: uuid.UUID | None = None,
) -> Document:
    content_type = _normalize_type(content_type, filename)
    if content_type not in ALLOWED_TYPES:
        raise InvalidInput("Only PDF and plain-text files are supported")
    if not data:
        raise InvalidInput("The file is empty")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise InvalidInput(f"Files are limited to {get_settings().max_upload_mb} MB")
    if replaces_document_id is not None:
        get_scoped(db, Document, ctx, replaces_document_id)

    sha256 = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(
        select(Document.id).where(
            Document.condominium_id == ctx.condominium_id,
            Document.sha256 == sha256,
            Document.status != DocumentStatus.INACTIVE,
        )
    )
    if duplicate:
        raise Conflict("This file is already in the knowledge base")

    document_id = uuid.uuid4()
    key = f"condominiums/{ctx.condominium_id}/documents/{document_id}{ALLOWED_TYPES[content_type]}"
    document = Document(
        id=document_id,
        condominium_id=ctx.condominium_id,
        title=title.strip(),
        storage_uri=store.put(key, data, content_type),
        mime_type=content_type,
        sha256=sha256,
        size_bytes=len(data),
        visibility=visibility,
        status=DocumentStatus.PENDING,
        replaces_document_id=replaces_document_id,
        uploaded_by_user_id=ctx.user.id,
    )
    db.add(document)
    audit.record_user_action(
        db, ctx, "document.uploaded", "document", document.id, visibility=visibility.value
    )
    db.commit()
    return document


def _normalize_type(content_type: str, filename: str) -> str:
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type in ALLOWED_TYPES:
        return content_type
    # Browsers often send application/octet-stream for .md / .txt.
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown"}.get(
        suffix, content_type
    )


def set_active(db: Session, ctx: CondoContext, document_id: uuid.UUID, active: bool) -> Document:
    document = get_scoped(db, Document, ctx, document_id)
    if active:
        if document.status != DocumentStatus.INACTIVE or document.superseded_by_id:
            raise Conflict("Only a deactivated document that was not replaced can be reactivated")
        document.status = DocumentStatus.READY if document.chunk_count else DocumentStatus.PENDING
    else:
        if document.status == DocumentStatus.INACTIVE:
            raise Conflict("Document is already inactive")
        document.status = DocumentStatus.INACTIVE
    audit.record_user_action(
        db, ctx, "document.activated" if active else "document.deactivated", "document", document.id
    )
    db.commit()
    return document


def mark_for_reindex(db: Session, ctx: CondoContext, document_id: uuid.UUID) -> Document:
    document = get_scoped(db, Document, ctx, document_id)
    if document.status not in (DocumentStatus.FAILED, DocumentStatus.READY):
        raise Conflict("Only failed or ready documents can be re-indexed")
    document.status = DocumentStatus.PENDING
    audit.record_user_action(db, ctx, "document.reindex_requested", "document", document.id)
    db.commit()
    return document


def list_documents(db: Session, ctx: CondoContext) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.condominium_id == ctx.condominium_id)
            .order_by(Document.status == DocumentStatus.INACTIVE, Document.created_at.desc())
        )
    )


def read_file(db: Session, ctx: CondoContext, store: BlobStore, document_id: uuid.UUID):
    document = get_scoped(db, Document, ctx, document_id)
    return document, store.get(document.storage_uri)


# --- Indexing (background job) -------------------------------------------------------------


@dataclass
class Page:
    number: int | None
    text: str


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    if mime_type == "application/pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ExtractionError("PDF protegido por senha")
            pages = [Page(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
        except PdfReadError as exc:
            raise ExtractionError("PDF inválido ou corrompido") from exc
    else:
        try:
            body = data.decode("utf-8")
        except UnicodeDecodeError:
            body = data.decode("latin-1")
        pages = [Page(None, body)]
    if not any(p.text.strip() for p in pages):
        raise ExtractionError(
            "Nenhum texto encontrado. PDFs digitalizados (imagem) ainda não são suportados."
        )
    return pages


def chunk_pages(pages: list[Page]) -> list[tuple[int | None, str | None, str]]:
    """Split into ~CHUNK_TARGET-character chunks on paragraph boundaries, never across pages.
    Each chunk carries its page and the section heading it falls under, for citations.
    A new section starts a new chunk."""
    chunks: list[tuple[int | None, str | None, str]] = []
    heading: str | None = None
    for page in pages:
        buffer: list[str] = []
        buffer_heading = heading
        for paragraph in _paragraphs(page.text):
            first_line = paragraph.splitlines()[0].strip()
            starts_section = bool(_HEADING.match(first_line))
            if starts_section:
                heading = first_line[:200]
            for piece in _split_long(paragraph):
                size = sum(len(p) for p in buffer)
                full = size + len(piece) > CHUNK_TARGET
                if buffer and (full or (starts_section and size >= MIN_SECTION_CHUNK)):
                    chunks.append((page.number, buffer_heading, "\n".join(buffer)))
                    buffer = []
                if not buffer or buffer_heading is None:
                    buffer_heading = heading
                buffer.append(piece)
                starts_section = False
        if buffer:
            chunks.append((page.number, buffer_heading, "\n".join(buffer)))
    return chunks


def _paragraphs(text_: str) -> list[str]:
    text_ = text_.replace("\r\n", "\n")
    parts = re.split(r"\n\s*\n", text_)
    if len(parts) == 1:  # PDFs often lose blank lines; fall back to single lines
        parts = text_.split("\n")
    return [re.sub(r"[ \t]+", " ", p).strip() for p in parts if p.strip()]


def _split_long(paragraph: str) -> list[str]:
    if len(paragraph) <= CHUNK_MAX:
        return [paragraph]
    sentences = re.split(r"(?<=[.;:!?])\s+", paragraph)
    pieces, current = [], ""
    for sentence in sentences:
        while len(sentence) > CHUNK_MAX:  # no punctuation at all
            pieces.append(sentence[:CHUNK_MAX])
            sentence = sentence[CHUNK_MAX:]
        if current and len(current) + len(sentence) > CHUNK_TARGET:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def index_document(
    db: Session,
    store: BlobStore,
    document_id: uuid.UUID,
    *,
    read: Callable[[Document], bytes] | None = None,
) -> None:
    """Extract, chunk and store a document. Safe to rerun: chunks are replaced. `read`
    fetches the file when it isn't in the blob store (documents kept in Drive)."""
    document = db.get(Document, document_id)
    if document is None or document.status in (DocumentStatus.READY, DocumentStatus.INACTIVE):
        return
    document.status = DocumentStatus.INDEXING
    document.error = None
    db.commit()
    try:
        data = read(document) if read else store.get(document.storage_uri)
        chunks = chunk_pages(extract_pages(data, document.mime_type))
    except ExtractionError as exc:
        document.status = DocumentStatus.FAILED
        document.error = str(exc)
        db.commit()
        return

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    for ordinal, (page, heading, content) in enumerate(chunks):
        db.add(
            DocumentChunk(
                condominium_id=document.condominium_id,
                document_id=document.id,
                ordinal=ordinal,
                page=page,
                heading=heading,
                content=content,
            )
        )
    document.status = DocumentStatus.READY
    document.chunk_count = len(chunks)
    document.indexed_at = _now()
    if document.replaces_document_id:
        old = db.get(Document, document.replaces_document_id)
        if old is not None and old.condominium_id == document.condominium_id:
            old.status = DocumentStatus.INACTIVE
            old.superseded_by_id = document.id
    db.commit()


# --- Search ----------------------------------------------------------------------------------


@dataclass
class SearchHit:
    document_id: uuid.UUID
    document_title: str
    document_date: datetime
    page: int | None
    heading: str | None
    content: str
    rank: float

    @property
    def citation(self) -> str:
        return f"{self.document_title}, p. {self.page}" if self.page else self.document_title


def search(
    db: Session,
    condominium_id: uuid.UUID,
    query: str,
    *,
    visibilities: tuple[DocumentVisibility, ...] = (DocumentVisibility.RESIDENTS,),
    limit: int = 5,
) -> list[SearchHit]:
    """Ranked full-text search over ready documents of one condominium.

    Terms are OR-ed, so a natural-language question still finds passages that share only
    some of its words. Ranking favours passages that match more of them.
    """
    if not query.strip():
        return []
    tsquery = cast(
        func.replace(cast(func.plainto_tsquery(_PT_CONFIG, query), Text), " & ", " | "), TSQUERY
    )
    rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery, 32).label("rank")
    rows = db.execute(
        select(DocumentChunk, Document.title, Document.created_at, rank)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.condominium_id == condominium_id,
            Document.condominium_id == condominium_id,
            Document.status == DocumentStatus.READY,
            Document.visibility.in_(visibilities),
            DocumentChunk.search_vector.op("@@")(tsquery),
        )
        .order_by(rank.desc(), DocumentChunk.ordinal)
        .limit(limit)
    ).all()
    return [
        SearchHit(c.document_id, title, created, c.page, c.heading, c.content, float(r))
        for c, title, created, r in rows
    ]
