import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.integrations.storage import BlobStore, get_blob_store
from app.models.enums import DocumentStatus, DocumentVisibility
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.operations import DocumentOut, DocumentSearchHit
from app.services import documents
from app.workers.runner import DOCUMENT_TOPIC

router = APIRouter(prefix="/condominiums/{condominium_id}/documents", tags=["documents"])

can_manage = require_permission(Permission.DOCUMENTS_MANAGE)


@router.get("", response_model=list[DocumentOut])
def list_documents(ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)):
    return documents.list_documents(db, ctx)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=200),
    visibility: DocumentVisibility = Form(DocumentVisibility.RESIDENTS),
    replaces_document_id: uuid.UUID | None = Form(None),
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    store: BlobStore = Depends(get_blob_store),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    """Store the file and queue indexing. The document is searchable once `ready`."""
    data = await file.read()
    document = documents.upload(
        db,
        ctx,
        store,
        title=title,
        filename=file.filename or "",
        content_type=file.content_type or "",
        data=data,
        visibility=visibility,
        replaces_document_id=replaces_document_id,
    )
    publisher.publish(DOCUMENT_TOPIC, {"document_id": str(document.id)})
    return document


@router.post("/{document_id}/deactivate", response_model=DocumentOut)
def deactivate(
    document_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return documents.set_active(db, ctx, document_id, active=False)


@router.post("/{document_id}/activate", response_model=DocumentOut)
def activate(
    document_id: uuid.UUID,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    document = documents.set_active(db, ctx, document_id, active=True)
    if document.status == DocumentStatus.PENDING:
        publisher.publish(DOCUMENT_TOPIC, {"document_id": str(document.id)})
    return document


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex(
    document_id: uuid.UUID,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    document = documents.mark_for_reindex(db, ctx, document_id)
    publisher.publish(DOCUMENT_TOPIC, {"document_id": str(document.id)})
    return document


@router.get("/{document_id}/file")
def download(
    document_id: uuid.UUID,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    store: BlobStore = Depends(get_blob_store),
):
    document, data = documents.read_file(db, ctx, store, document_id)
    extension = documents.ALLOWED_TYPES.get(document.mime_type, "")
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="documento-{document.id}{extension}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/search/preview", response_model=list[DocumentSearchHit])
def search_preview(
    q: str = Query(..., min_length=2, max_length=300),
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    """What the assistant would find for a resident's question (residents' documents only)."""
    return [
        DocumentSearchHit(
            document_id=h.document_id, citation=h.citation, section=h.heading, excerpt=h.content
        )
        for h in documents.search(db, ctx.condominium_id, q)
    ]
