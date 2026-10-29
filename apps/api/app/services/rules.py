"""The condominium's rules documents for sheet-backed condominiums (ADR 0015).

The manager sends a PDF or text file to Zela on WhatsApp. Zela saves it in the
condominium's Drive folder (the record, and a file Zela created, so the drive.file scope
can read it back), then indexes its text with the Milestone 3 search (ADR 0006). Anyone
registered can then ask about the rules and get answers that cite the document.
Documents are untrusted: their text only reaches the model as quoted reference material.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.jobs import JobPublisher
from app.integrations.google.base import Google
from app.integrations.storage import BlobStore
from app.integrations.whatsapp.sender import MediaError, WhatsAppSender
from app.integrations.whatsapp.templates import DOCUMENT_STATUS
from app.models import Condominium, Document
from app.models.enums import ActorType, DocumentStatus, DocumentVisibility
from app.registers.table import normalize_header
from app.services import audit, documents, drive, notifications
from app.services.people import Person, PersonRole

DOCUMENT_TOPIC = "document-index"
DRIVE_PREFIX = "gdrive:"

NOT_MANAGER = (
    "Recebi o arquivo, mas só o síndico pode enviar documentos para o Zela. Se precisar de "
    "algo, é só escrever aqui."
)
UNSUPPORTED = (
    "Consigo ler documentos em PDF ou texto (.txt). Envie o regimento, a convenção ou um "
    "aviso em um desses formatos."
)
TOO_LARGE = "O arquivo passa de {mb} MB. Envie uma versão menor."
DOWNLOAD_FAILED = "Não consegui baixar o arquivo do WhatsApp. Pode enviar de novo?"
ALREADY = 'Esse arquivo já está nos documentos do condomínio ("{title}").'
DRIVE_DOWN = "Não consegui salvar o arquivo no Google Drive: {reason}"
RECEIVED = (
    'Recebi "{title}" e salvei na pasta do Zela no seu Google Drive. Vou ler o documento '
    "e aviso por aqui quando já der para perguntar sobre ele."
)
REPLACES = " Ele substitui a versão anterior com o mesmo nome."
READY = "pronto. Os moradores já podem perguntar sobre ele por aqui."
FAILED = "não consegui ler o texto ({reason}). Envie uma versão em PDF com texto selecionável."


def _title(document: dict) -> str:
    caption = " ".join((document.get("caption") or "").split())
    filename = document.get("filename") or "Documento"
    return (caption or filename.rsplit(".", 1)[0]).strip()[:200] or "Documento"


def active(db: Session, condominium_id: uuid.UUID) -> list[Document]:
    """Documents that are searchable or on their way, oldest first."""
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.condominium_id == condominium_id,
                Document.status != DocumentStatus.INACTIVE,
                Document.superseded_by_id.is_(None),
            )
            .order_by(Document.created_at)
        )
    )


def receive(
    db: Session,
    google: Google,
    sender: WhatsAppSender,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    message: dict,
) -> str:
    """Handles a document message; returns the reply. Only the manager may add documents."""
    if person.role != PersonRole.MANAGER:
        return NOT_MANAGER
    sent = message.get("document") or {}
    filename = sent.get("filename") or "documento"
    mime_type = documents._normalize_type(sent.get("mime_type", ""), filename)
    if mime_type not in documents.ALLOWED_TYPES or not sent.get("id"):
        return UNSUPPORTED
    max_mb = get_settings().max_upload_mb
    try:
        data = sender.download_media(sent["id"], max_mb * 1024 * 1024)
    except MediaError as exc:
        return TOO_LARGE.format(mb=max_mb) if str(exc) == "too large" else DOWNLOAD_FAILED
    if not data:
        return DOWNLOAD_FAILED

    title = _title(sent)
    sha256 = hashlib.sha256(data).hexdigest()
    current = active(db, condo.id)
    same_file = next((d for d in current if d.sha256 == sha256), None)
    if same_file is not None:
        return ALREADY.format(title=same_file.title)
    previous = next(
        (
            d
            for d in current
            if d.status == DocumentStatus.READY
            and normalize_header(d.title) == normalize_header(title)
        ),
        None,
    )

    # Keyed by the WhatsApp message, so a retried message finds the file it uploaded.
    props = {"zela_condominium": str(condo.id), "zela_item": f"document:{message['id']}"}
    try:
        file_id = drive.run_in_drive(
            db,
            google,
            condo.id,
            lambda ws, folder: (
                ws.find_file(props, mime_type=mime_type)
                or ws.upload_file(
                    filename, mime_type=mime_type, data=data, folder_id=folder, app_properties=props
                )
            ),
        )
    except drive.RegisterUnavailable as exc:
        return DRIVE_DOWN.format(reason=exc.message)
    document = Document(
        id=uuid.uuid4(),
        condominium_id=condo.id,
        title=title,
        storage_uri=DRIVE_PREFIX + file_id,
        mime_type=mime_type,
        sha256=sha256,
        size_bytes=len(data),
        visibility=DocumentVisibility.RESIDENTS,
        status=DocumentStatus.PENDING,
        replaces_document_id=previous.id if previous else None,
    )
    db.add(document)
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="document.received",
        entity_type="document",
        entity_id=document.id,
        data={"via": "whatsapp", "replaces": str(previous.id) if previous else None},
    )
    db.commit()
    publisher.publish(DOCUMENT_TOPIC, {"document_id": str(document.id)})
    return RECEIVED.format(title=title) + (REPLACES if previous else "")


def index(
    db: Session,
    google: Google,
    store: BlobStore,
    publisher: JobPublisher,
    document_id: uuid.UUID,
) -> None:
    """The document-index job. Documents kept in Drive are read from there, and the
    manager is told the outcome. If Drive can't be read, the document goes back to
    pending and this raises, so the job is retried."""
    document = db.get(Document, document_id)
    if document is None:
        return
    if not document.storage_uri.startswith(DRIVE_PREFIX):
        documents.index_document(db, store, document_id)
        return
    if document.status in (DocumentStatus.READY, DocumentStatus.INACTIVE):
        return

    def read(doc: Document) -> bytes:
        file_id = doc.storage_uri.removeprefix(DRIVE_PREFIX)
        return drive.run_in_drive(
            db, google, doc.condominium_id, lambda ws, _: ws.download_file(file_id)
        )

    try:
        documents.index_document(db, store, document_id, read=read)
    except drive.RegisterUnavailable:
        db.rollback()
        document = db.get(Document, document_id)
        document.status = DocumentStatus.PENDING
        db.commit()
        raise
    db.refresh(document)
    condo = db.get(Condominium, document.condominium_id)
    if not (condo.manager_phone_e164 and condo.manager_phone_confirmed_at):
        return
    ok = document.status == DocumentStatus.READY
    notifications.enqueue(
        db,
        publisher,
        condominium_id=condo.id,
        recipient_e164=condo.manager_phone_e164,
        template=DOCUMENT_STATUS.name,
        params={
            "title": document.title,
            "status": READY if ok else FAILED.format(reason=(document.error or "").rstrip(".")),
        },
        idempotency_key=f"document:{document.id}:{document.status}",
    )


def remove(db: Session, condo: Condominium, document: Document, actor_id: uuid.UUID) -> None:
    """Stops answering from a document. The file stays in Drive."""
    document.status = DocumentStatus.INACTIVE
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.AGENT,
        actor_id=actor_id,
        action="document.removed",
        entity_type="document",
        entity_id=document.id,
        data={"via": "whatsapp"},
    )
    db.commit()
