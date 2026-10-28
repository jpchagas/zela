import uuid

import pytest
from sqlalchemy import select

from app.models import Document, DocumentChunk
from app.models.enums import DocumentStatus
from app.services import documents
from app.workers.runner import DOCUMENT_TOPIC
from tests.factories import auth
from tests.pdf import make_pdf

MANAGER = auth("manager.a@example.com")

REGIMENTO = make_pdf(
    [
        "REGIMENTO INTERNO\nCAPÍTULO I - DA PISCINA\n"
        "Art. 1 A piscina funciona de terça a domingo, das 8h às 22h.\n"
        "Art. 2 É proibido o uso de copos de vidro na área da piscina.",
        "CAPÍTULO II - DO SILÊNCIO\nArt. 3 O horário de silêncio é das 22h às 8h.\n"
        "Art. 4 Mudanças só podem ocorrer de segunda a sábado, das 8h às 18h.",
    ]
)


def _upload(
    client,
    condo,
    data=REGIMENTO,
    *,
    title="Regimento Interno",
    filename="regimento.pdf",
    content_type="application/pdf",
    headers=MANAGER,
    **form,
):
    return client.post(
        f"/v1/condominiums/{condo.id}/documents",
        data={"title": title, **form},
        files={"file": (filename, data, content_type)},
        headers=headers,
    )


def _index_all(db, store, publisher):
    for job in publisher.take(DOCUMENT_TOPIC):
        documents.index_document(db, store, uuid.UUID(job["document_id"]))


@pytest.fixture
def regimento(client, db, world, store, publisher):
    body = _upload(client, world.condo_a).json()
    _index_all(db, store, publisher)
    return db.get(Document, body["id"])


def test_upload_queues_indexing_and_indexes_pages_and_sections(client, db, world, store, publisher):
    response = _upload(client, world.condo_a)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert publisher.jobs == [(DOCUMENT_TOPIC, {"document_id": response.json()["id"]})]

    _index_all(db, store, publisher)
    document = db.get(Document, response.json()["id"])
    assert document.status == DocumentStatus.READY
    chunks = db.scalars(select(DocumentChunk).order_by(DocumentChunk.ordinal)).all()
    assert [(c.page, c.heading) for c in chunks] == [
        (1, "CAPÍTULO I - DA PISCINA"),
        (2, "CAPÍTULO II - DO SILÊNCIO"),
    ]
    assert document.chunk_count == 2


def test_plain_text_upload(client, db, world, store, publisher):
    text = "AVISO\n\nA coleta de lixo reciclável é às quartas-feiras.".encode()
    response = _upload(
        client,
        world.condo_a,
        text,
        title="Aviso coleta",
        filename="aviso.txt",
        content_type="application/octet-stream",
    )
    assert response.status_code == 201 and response.json()["mime_type"] == "text/plain"
    _index_all(db, store, publisher)
    [hit] = documents.search(db, world.condo_a.id, "quando é a coleta do lixo reciclavel?")
    assert hit.citation == "Aviso coleta"


@pytest.mark.parametrize(
    "data,filename,content_type,status",
    [
        (b"MZ\x90\x00", "virus.exe", "application/x-msdownload", 422),
        (b"", "vazio.pdf", "application/pdf", 422),
    ],
)
def test_upload_validation(client, world, store, publisher, data, filename, content_type, status):
    assert (
        _upload(
            client, world.condo_a, data, filename=filename, content_type=content_type
        ).status_code
        == status
    )


def test_same_file_twice_is_rejected(client, world, store, publisher):
    assert _upload(client, world.condo_a).status_code == 201
    assert _upload(client, world.condo_a).status_code == 409


def test_scanned_or_broken_pdfs_fail_with_a_reason(client, db, world, store, publisher):
    scanned = _upload(
        client, world.condo_a, make_pdf([""]), title="Escaneado", filename="a.pdf"
    ).json()
    broken = _upload(
        client, world.condo_a, b"%PDF-1.4 garbage", title="Quebrado", filename="b.pdf"
    ).json()
    _index_all(db, store, publisher)
    assert db.get(Document, scanned["id"]).status == DocumentStatus.FAILED
    assert "digitalizados" in db.get(Document, scanned["id"]).error
    assert db.get(Document, broken["id"]).status == DocumentStatus.FAILED


def test_search_is_accent_and_inflection_insensitive_and_ranked(db, world, regimento):
    hits = documents.search(db, world.condo_a.id, "qual o horario de funcionamento das piscinas?")
    assert hits[0].citation == "Regimento Interno, p. 1"
    assert "8h às 22h" in hits[0].content
    # Lexical ties are possible; what matters is that the passage reaches the model.
    moving = documents.search(db, world.condo_a.id, "posso fazer mudanca no domingo")
    assert any("Mudanças" in h.content and h.page == 2 for h in moving)


def test_search_never_crosses_condominiums(db, world, regimento):
    assert documents.search(db, world.condo_b.id, "piscina") == []


def test_staff_only_and_inactive_documents_are_not_searched(
    client, db, world, store, publisher, regimento
):
    internal = make_pdf(["Senha do portão de serviço: 4321. Uso exclusivo da equipe."])
    _upload(client, world.condo_a, internal, title="Procedimentos internos", visibility="staff")
    _index_all(db, store, publisher)
    assert documents.search(db, world.condo_a.id, "senha do portão") == []

    client.post(
        f"/v1/condominiums/{world.condo_a.id}/documents/{regimento.id}/deactivate", headers=MANAGER
    )
    assert documents.search(db, world.condo_a.id, "piscina") == []
    client.post(
        f"/v1/condominiums/{world.condo_a.id}/documents/{regimento.id}/activate", headers=MANAGER
    )
    assert documents.search(db, world.condo_a.id, "piscina")


def test_replacement_takes_over_only_once_indexed(client, db, world, store, publisher, regimento):
    new = make_pdf(
        ["CAPÍTULO I - DA PISCINA\nArt. 1 A piscina funciona todos os dias, das 7h às 23h."]
    )
    body = _upload(
        client,
        world.condo_a,
        new,
        title="Regimento Interno 2026",
        replaces_document_id=str(regimento.id),
    ).json()
    db.refresh(regimento)
    assert regimento.status == DocumentStatus.READY  # still answering until the new one is ready

    _index_all(db, store, publisher)
    db.refresh(regimento)
    assert regimento.status == DocumentStatus.INACTIVE
    assert str(regimento.superseded_by_id) == body["id"]
    assert [h.citation for h in documents.search(db, world.condo_a.id, "horário da piscina")] == [
        "Regimento Interno 2026, p. 1"
    ]


def test_permissions_and_isolation(client, world, store, publisher, regimento):
    base = f"/v1/condominiums/{world.condo_a.id}/documents"
    assert client.get(base, headers=auth("staff.a@example.com")).status_code == 403
    assert (
        _upload(
            client,
            world.condo_a,
            b"x",
            filename="x.txt",
            content_type="text/plain",
            headers=auth("manager.b@example.com"),
        ).status_code
        == 404
    )
    foreign = client.get(
        f"/v1/condominiums/{world.condo_b.id}/documents/{regimento.id}/file",
        headers=auth("manager.b@example.com"),
    )
    assert foreign.status_code == 404


def test_download_and_search_preview(client, world, regimento):
    base = f"/v1/condominiums/{world.condo_a.id}/documents"
    file = client.get(f"{base}/{regimento.id}/file", headers=MANAGER)
    assert file.status_code == 200 and file.content == REGIMENTO
    preview = client.get(f"{base}/search/preview", params={"q": "silêncio"}, headers=MANAGER).json()
    assert preview[0]["citation"] == "Regimento Interno, p. 2"


def test_reindex_after_failure(client, db, world, store, publisher):
    body = _upload(client, world.condo_a, make_pdf([""]), title="Vazio", filename="v.pdf").json()
    _index_all(db, store, publisher)
    response = client.post(
        f"/v1/condominiums/{world.condo_a.id}/documents/{body['id']}/reindex", headers=MANAGER
    )
    assert response.json()["status"] == "pending"
    assert publisher.take(DOCUMENT_TOPIC) == [{"document_id": body["id"]}]
