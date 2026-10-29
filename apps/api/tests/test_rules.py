"""Rules Q&A from documents the manager sends on WhatsApp (ADR 0015)."""

import json
import uuid

import pytest
from sqlalchemy import select

from app.core import crypto
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.scripted import RuleBasedLLM, ScriptedLLM, call, say
from app.models import AuditEvent, Document, DriveConnection, NotificationEvent
from app.models.enums import DocumentStatus
from app.services import documents, drive, people, rules
from tests.factories import FakePublisher
from tests.pdf import make_pdf
from tests.sheets import MANAGER_PHONE, add_row, confirm_manager, connect_drive, tab
from tests.whatsapp import deliver, outbound

OWNER = "owner1@example.com"
ACCOUNT = "sindico@example.com"
ANA = "+5511987654321"
REGIMENTO = make_pdf(
    [
        "REGIMENTO INTERNO\nCAPÍTULO I - DA PISCINA\n"
        "Art. 1 A piscina funciona de terça a domingo, das 8h às 22h.\n"
        "Art. 2 É proibido o uso de copos de vidro na área da piscina.",
        "CAPÍTULO II - DO SILÊNCIO\nArt. 3 O horário de silêncio é das 22h às 8h.\n"
        "Art. 4 Mudanças só podem ocorrer de segunda a sábado, das 8h às 18h.",
    ]
)


@pytest.fixture
def condo(client, db, world, google, publisher):
    connect_drive(client, db, google, world.condo_a, OWNER)
    add_row(
        tab(db, google, world.condo_a),
        zela_id="P-ANA",
        name="Ana Souza",
        whatsapp=ANA,
        unit="302",
        role="Morador",
    )
    confirm_manager(db, world.condo_a)
    return world.condo_a


@pytest.fixture
def sender():
    return RecordingSender(media={"m-reg": REGIMENTO, "m-txt": b"Aviso: piscina fechada"})


@pytest.fixture
def jobs():
    return FakePublisher()


def _send_file(db, condo, google, sender, jobs, *, phone=MANAGER_PHONE, **document):
    document = {
        "id": "m-reg",
        "filename": "Regimento Interno.pdf",
        "mime_type": "application/pdf",
        **document,
    }
    deliver(
        db,
        condo,
        None,
        sender=sender,
        google=google,
        from_e164=phone,
        publisher=jobs,
        llm=ScriptedLLM([]),  # the model is never called for files
        document=document,
    )
    return outbound(db)[-1].body


def _index_all(db, google, store, jobs):
    for job in jobs.take(rules.DOCUMENT_TOPIC):
        rules.index(db, google, store, jobs, uuid_of(job))


def uuid_of(job):
    return uuid.UUID(job["document_id"])


def _ask(db, condo, google, script, phone=ANA):
    llm = ScriptedLLM(script)
    deliver(
        db, condo, "pergunta", sender=RecordingSender(), llm=llm, google=google, from_e164=phone
    )
    return llm.sessions[0]


def _say_last(session):
    return say("resultado: " + session.outcomes[-1].content)


def test_the_manager_sends_the_regulations_and_residents_ask(
    db, condo, google, sender, jobs, store
):
    reply = _send_file(db, condo, google, sender, jobs)
    assert reply == rules.RECEIVED.format(title="Regimento Interno")
    [saved] = [f for f in google.files_of(ACCOUNT) if f.name == "Regimento Interno.pdf"]
    connection = db.scalar(select(DriveConnection))
    assert saved.parents == [connection.folder_id] and saved.content == REGIMENTO

    document = db.scalar(select(Document))
    assert document.status == DocumentStatus.PENDING
    assert document.storage_uri == f"gdrive:{saved.id}"
    _index_all(db, google, store, jobs)
    db.refresh(document)
    assert document.status == DocumentStatus.READY and document.chunk_count >= 2

    [ready] = db.scalars(
        select(NotificationEvent).where(NotificationEvent.template == "zela_document_status")
    ).all()
    assert ready.recipient_e164 == MANAGER_PHONE
    assert ready.data["params"] == {"title": "Regimento Interno", "status": rules.READY}

    session = _ask(db, condo, google, [call("search_rules", query="horário da piscina"), _say_last])
    results = json.loads(session.outcomes[0].content)["results"]
    assert results[0]["source"] == "Regimento Interno, p. 1"
    assert "8h às 22h" in results[0]["excerpt"]

    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "document.received"))
    assert event.entity_id == document.id and "Regimento" not in json.dumps(event.data)


def test_only_the_manager_can_add_documents(db, condo, google, sender, jobs):
    assert _send_file(db, condo, google, sender, jobs, phone=ANA) == rules.NOT_MANAGER
    assert db.scalar(select(Document)) is None and jobs.take(rules.DOCUMENT_TOPIC) == []


@pytest.mark.parametrize(
    ("document", "reply"),
    [
        ({"filename": "foto.jpg", "mime_type": "image/jpeg"}, rules.UNSUPPORTED),
        ({"id": "m-missing"}, rules.DOWNLOAD_FAILED),
    ],
)
def test_files_that_cannot_be_used(db, condo, google, sender, jobs, document, reply):
    assert _send_file(db, condo, google, sender, jobs, **document) == reply
    assert db.scalar(select(Document)) is None


def test_the_same_file_twice_and_a_new_version(db, condo, google, sender, jobs, store):
    _send_file(db, condo, google, sender, jobs)
    _index_all(db, google, store, jobs)
    again = _send_file(db, condo, google, sender, jobs)
    assert again == rules.ALREADY.format(title="Regimento Interno")

    sender.media["m-new"] = make_pdf(["REGIMENTO INTERNO\nArt. 1 A piscina abre às 7h."])
    newer = _send_file(db, condo, google, sender, jobs, id="m-new")
    assert newer.endswith(rules.REPLACES)
    _index_all(db, google, store, jobs)
    new = db.scalar(select(Document).where(Document.replaces_document_id.is_not(None)))
    old = db.get(Document, new.replaces_document_id)
    assert old.status == DocumentStatus.INACTIVE and old.superseded_by_id == new.id
    session = _ask(db, condo, google, [call("search_rules", query="piscina abre"), _say_last])
    excerpts = [r["excerpt"] for r in json.loads(session.outcomes[0].content)["results"]]
    assert excerpts and all("7h" in e for e in excerpts)


def test_a_caption_names_the_document(db, condo, google, sender, jobs, store):
    _send_file(
        db,
        condo,
        google,
        sender,
        jobs,
        id="m-txt",
        filename="aviso.txt",
        mime_type="text/plain",
        caption="Aviso da piscina",
    )
    _index_all(db, google, store, jobs)
    assert db.scalar(select(Document)).title == "Aviso da piscina"


def test_a_scanned_pdf_is_reported_to_the_manager(db, condo, google, sender, jobs, store):
    sender.media["m-scan"] = make_pdf([""])
    _send_file(db, condo, google, sender, jobs, id="m-scan")
    _index_all(db, google, store, jobs)
    assert db.scalar(select(Document)).status == DocumentStatus.FAILED
    notice = db.scalar(
        select(NotificationEvent).where(NotificationEvent.template == "zela_document_status")
    )
    assert notice.data["params"]["status"].startswith("não consegui ler o texto (Nenhum texto")


def test_indexing_waits_when_drive_cannot_be_read(db, condo, google, sender, jobs, store):
    _send_file(db, condo, google, sender, jobs)
    connection = db.scalar(select(DriveConnection))
    google.revoked.add(crypto.decrypt_secret(connection.refresh_token_encrypted))
    [job] = jobs.take(rules.DOCUMENT_TOPIC)
    with pytest.raises(drive.RegisterUnavailable):
        rules.index(db, google, store, jobs, uuid_of(job))
    assert db.scalar(select(Document)).status == DocumentStatus.PENDING


def test_a_retried_message_uploads_once(db, condo, google, sender, jobs):
    """The worker crashed after the upload but before committing: the retry finds the
    file by the message's ID instead of uploading it again."""
    document = {"id": "m-reg", "filename": "Regimento Interno.pdf", "mime_type": "application/pdf"}
    manager = people.identify(db, google, condo, MANAGER_PHONE)
    for _ in range(2):
        db.query(Document).delete()  # what the crash rolled back
        db.commit()
        rules.receive(
            db,
            google,
            sender,
            jobs,
            condo=condo,
            person=manager,
            message={"id": "wamid.same", "document": document},
        )
    assert len([f for f in google.files_of(ACCOUNT) if f.name == "Regimento Interno.pdf"]) == 1


def test_answers_say_when_nothing_is_found(db, condo, google):
    session = _ask(db, condo, google, [call("search_rules", query="churrasqueira"), _say_last])
    assert json.loads(session.outcomes[0].content) == {
        "results": [],
        "note": "Nada encontrado nos documentos do condomínio.",
    }


def test_the_manager_lists_and_removes_documents(db, condo, google, sender, jobs, store):
    _send_file(db, condo, google, sender, jobs)
    _index_all(db, google, store, jobs)
    listing = _ask(db, condo, google, [call("list_documents"), _say_last], phone=MANAGER_PHONE)
    [listed] = json.loads(listing.outcomes[0].content)["documents"]
    assert (listed["title"], listed["status"]) == ("Regimento Interno", "pronto")

    refused = _ask(db, condo, google, [call("remove_document", title="Regimento"), _say_last])
    assert refused.outcomes[0].is_error and "Unknown tool" in refused.outcomes[0].content
    removed = _ask(
        db,
        condo,
        google,
        [call("remove_document", title="regimento"), _say_last],
        phone=MANAGER_PHONE,
    )
    assert json.loads(removed.outcomes[0].content) == {"removed": "Regimento Interno"}
    search = _ask(db, condo, google, [call("search_rules", query="piscina"), _say_last])
    assert json.loads(search.outcomes[0].content)["results"] == []
    assert any(f.name == "Regimento Interno.pdf" for f in google.files_of(ACCOUNT))  # kept


def test_documents_are_scoped_to_their_condominium(
    client, db, world, google, sender, jobs, store, condo
):
    _send_file(db, condo, google, sender, jobs)
    _index_all(db, google, store, jobs)
    assert documents.search(db, world.condo_b.id, "piscina") == []
    assert documents.search(db, condo.id, "piscina")


def test_the_dev_stand_in_answers_from_documents(db, condo, google, sender, jobs, store):
    _send_file(db, condo, google, sender, jobs)
    _index_all(db, google, store, jobs)
    deliver(
        db,
        condo,
        "qual o horário da piscina?",
        sender=RecordingSender(),
        llm=RuleBasedLLM(),
        google=google,
        from_e164=ANA,
    )
    reply = outbound(db)[-1].body
    assert "Regimento Interno, p. 1" in reply and "8h às 22h" in reply
