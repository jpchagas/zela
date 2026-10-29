"""Connecting a condominium to Google Drive and creating its registers (ADR 0010), against
the in-memory FakeGoogle."""

from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, select

from app.core import crypto
from app.integrations.google.base import FOLDER_MIME, SCOPES, SPREADSHEET_MIME
from app.integrations.google.client import GoogleClient
from app.integrations.google.factory import get_google
from app.main import app
from app.models import AuditEvent, DriveConnection, SheetRegister
from app.models.enums import DriveStatus, RegisterKind, RegisterStatus
from app.registers.specs import PEOPLE, REGISTERS
from app.services import drive
from tests.factories import auth

OWNER = "owner1@example.com"
ACCOUNT = "sindico@example.com"


def _state(client, condo, email=OWNER) -> str:
    response = client.post(f"/v1/condominiums/{condo.id}/drive/connect", headers=auth(email))
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]


def _callback(client, **params):
    return client.get("/oauth/google/callback", params=params, follow_redirects=False)


def connect(client, google, condo, *, account=ACCOUNT, scopes=SCOPES):
    response = _callback(
        client, code=google.issue_code(account, scopes), state=_state(client, condo)
    )
    assert response.status_code == 303
    return response


def _status(client, condo):
    response = client.get(f"/v1/condominiums/{condo.id}/drive", headers=auth(OWNER))
    assert response.status_code == 200, response.text
    return response.json()


def _connection(db, condo) -> DriveConnection:
    return db.scalar(select(DriveConnection).where(DriveConnection.condominium_id == condo.id))


def test_connect_stores_an_encrypted_grant_and_queues_setup(client, db, world, google, publisher):
    response = connect(client, google, world.condo_a)
    assert response.headers["location"] == (
        f"http://localhost:3000/c/{world.condo_a.id}?drive=connected"
    )

    connection = _connection(db, world.condo_a)
    assert connection.account_email == ACCOUNT
    assert connection.status == DriveStatus.ACTIVE
    assert "refresh-" not in connection.refresh_token_encrypted
    assert crypto.decrypt_secret(connection.refresh_token_encrypted).startswith("refresh-")
    assert publisher.take(drive.DRIVE_SETUP_TOPIC) == [{"condominium_id": str(world.condo_a.id)}]

    body = _status(client, world.condo_a)
    assert body["connected"] and body["account_email"] == ACCOUNT
    assert [r["status"] for r in body["registers"]] == ["pending"] * len(REGISTERS)
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "drive.connected"))
    assert event.data == {"provider": "google", "account_changed": False}


def test_setup_creates_the_folder_and_every_register(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)

    [folder] = google.files_of(ACCOUNT, FOLDER_MIME)
    assert folder.name == "Zela · Residencial Aurora"
    sheets = {f.name: f for f in google.files_of(ACCOUNT, SPREADSHEET_MIME)}
    assert set(sheets) == {spec.title for spec in REGISTERS.values()}
    people = sheets["Pessoas"]
    assert people.parents == [folder.id]
    tab = people.tabs[0]
    assert tab.title == "Pessoas" and tab.rows == [PEOPLE.headers]
    assert tab.header_protected
    assert tab.choices[PEOPLE.headers.index("Papel")] == [
        "Síndico",
        "Proprietário",
        "Morador",
        "Funcionário",
    ]

    body = _status(client, world.condo_a)
    assert body["folder_url"] == f"https://drive.google.com/drive/folders/{folder.id}"
    assert all(r["status"] == "ready" and r["url"] for r in body["registers"])


def test_setup_is_idempotent_and_finds_its_files_again(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    drive.setup_registers(db, google, world.condo_a.id)
    first_ids = {f.id for f in google.files_of(ACCOUNT)}
    assert len(first_ids) == 1 + len(REGISTERS)

    # Disconnecting forgets the IDs; reconnecting the same account must not duplicate files.
    assert (
        client.delete(f"/v1/condominiums/{world.condo_a.id}/drive", headers=auth(OWNER)).status_code
        == 204
    )
    google.revoked.clear()
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    assert {f.id for f in google.files_of(ACCOUNT)} == first_ids


def test_a_trashed_register_is_recreated(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    [old] = [f for f in google.files_of(ACCOUNT) if f.name == "Encomendas"]
    old.trashed = True

    client.post(f"/v1/condominiums/{world.condo_a.id}/drive/sync", headers=auth(OWNER))
    drive.setup_registers(db, google, world.condo_a.id)
    live = [f for f in google.files_of(ACCOUNT) if f.name == "Encomendas" and not f.trashed]
    assert len(live) == 1 and live[0].id != old.id


def test_missing_columns_are_added_back_at_the_end(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    register = db.scalar(select(SheetRegister).where(SheetRegister.kind == RegisterKind.PEOPLE))
    tab = google.tab(register.spreadsheet_id)
    tab.rows[0] = [h for h in tab.rows[0] if h != "Observações"]

    drive.setup_registers(db, google, world.condo_a.id)
    assert tab.rows[0][-1] == "Observações"
    assert tab.rows[0].count("Observações") == 1


def test_a_sheet_without_its_id_column_fails_with_a_message(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    register = db.scalar(select(SheetRegister).where(SheetRegister.kind == RegisterKind.PEOPLE))
    google.tab(register.spreadsheet_id).rows[0][0] = "Código"

    drive.setup_registers(db, google, world.condo_a.id)
    by_kind = {r["kind"]: r for r in _status(client, world.condo_a)["registers"]}
    assert by_kind["people"]["status"] == "failed"
    assert "ID Zela" in by_kind["people"]["last_error"]
    assert by_kind["deliveries"]["status"] == "ready"


def test_a_revoked_grant_asks_the_manager_to_reconnect(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    connection = _connection(db, world.condo_a)
    google.revoked.add(crypto.decrypt_secret(connection.refresh_token_encrypted))

    drive.setup_registers(db, google, world.condo_a.id)
    body = _status(client, world.condo_a)
    assert body["status"] == "reauth_required"
    assert all(
        r["status"] == "failed" and r["last_error"] == drive.MSG_REAUTH for r in body["registers"]
    )
    response = client.post(f"/v1/condominiums/{world.condo_a.id}/drive/sync", headers=auth(OWNER))
    assert response.status_code == 409

    # Reconnecting clears it.
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    assert _status(client, world.condo_a)["status"] == "active"


def test_an_unreadable_stored_grant_asks_to_reconnect(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    _connection(db, world.condo_a).refresh_token_encrypted = "encrypted-with-an-old-key"
    db.commit()
    drive.setup_registers(db, google, world.condo_a.id)
    assert _status(client, world.condo_a)["status"] == "reauth_required"


def test_only_organization_admins_can_connect(client, world, google):
    for email in ("manager.a@example.com", "staff.a@example.com"):
        response = client.post(
            f"/v1/condominiums/{world.condo_a.id}/drive/connect", headers=auth(email)
        )
        assert response.status_code == 403


def test_connect_to_a_foreign_condominium_is_404(client, world, google):
    response = client.post(
        f"/v1/condominiums/{world.condo_c.id}/drive/connect", headers=auth(OWNER)
    )
    assert response.status_code == 404


def test_tampered_or_expired_state_is_rejected(client, db, world, google, publisher):
    state = _state(client, world.condo_a)
    expired = crypto.sign(
        {"c": str(world.condo_a.id), "u": str(world.owner1.id)},
        purpose=drive.STATE_PURPOSE,
        ttl_seconds=-1,
    )
    for bad in (state[:-2] + "xx", expired, ""):
        response = _callback(client, code=google.issue_code(), state=bad)
        assert response.headers["location"] == "http://localhost:3000/?drive_error=invalid_state"
    assert db.scalar(select(func.count()).select_from(DriveConnection)) == 0


def test_callback_rechecks_that_the_user_may_connect(client, db, world, google, publisher):
    # A validly signed state for someone who isn't an org admin of the condominium.
    state = crypto.sign(
        {"c": str(world.condo_a.id), "u": str(world.manager_a.id)},
        purpose=drive.STATE_PURPOSE,
        ttl_seconds=600,
    )
    response = _callback(client, code=google.issue_code(), state=state)
    assert response.headers["location"].endswith("?drive_error=forbidden")
    assert db.scalar(select(func.count()).select_from(DriveConnection)) == 0


def test_declined_consent_returns_to_the_condominium(client, world, google):
    response = _callback(client, error="access_denied", state=_state(client, world.condo_a))
    assert response.headers["location"] == (
        f"http://localhost:3000/c/{world.condo_a.id}?drive_error=denied"
    )


def test_a_grant_without_drive_access_is_refused_and_revoked(client, db, world, google, publisher):
    response = connect(client, google, world.condo_a, scopes=("openid", "email"))
    assert response.headers["location"].endswith("?drive_error=scope_missing")
    assert len(google.revoked) == 1
    assert db.scalar(select(func.count()).select_from(DriveConnection)) == 0
    assert publisher.take(drive.DRIVE_SETUP_TOPIC) == []


def test_switching_accounts_starts_the_registers_over(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    old_token = crypto.decrypt_secret(_connection(db, world.condo_a).refresh_token_encrypted)

    connect(client, google, world.condo_a, account="outra@example.com")
    assert old_token in google.revoked
    assert all(
        r["status"] == "pending" and r["url"] is None
        for r in _status(client, world.condo_a)["registers"]
    )
    drive.setup_registers(db, google, world.condo_a.id)
    assert len(google.files_of("outra@example.com", SPREADSHEET_MIME)) == len(REGISTERS)
    event = db.scalars(select(AuditEvent).where(AuditEvent.action == "drive.connected")).all()[-1]
    assert event.data["account_changed"] is True


def test_disconnect_revokes_and_leaves_the_sheets_in_drive(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    token = crypto.decrypt_secret(_connection(db, world.condo_a).refresh_token_encrypted)

    response = client.delete(f"/v1/condominiums/{world.condo_a.id}/drive", headers=auth(OWNER))
    assert response.status_code == 204
    assert token in google.revoked
    assert db.scalar(select(func.count()).select_from(SheetRegister)) == 0
    assert len(google.files_of(ACCOUNT)) == 1 + len(REGISTERS)
    assert _status(client, world.condo_a) == {
        "configured": True,
        "connected": False,
        "status": None,
        "account_email": None,
        "connected_at": None,
        "folder_url": None,
        "registers": [],
    }


def test_connect_without_oauth_credentials_is_409(client, world):
    unconfigured = GoogleClient(client_id="", client_secret="", redirect_uri="http://x")
    app.dependency_overrides[get_google] = lambda: unconfigured
    response = client.post(
        f"/v1/condominiums/{world.condo_a.id}/drive/connect", headers=auth(OWNER)
    )
    assert response.status_code == 409
    assert (
        client.get(f"/v1/condominiums/{world.condo_a.id}/drive", headers=auth(OWNER)).json()[
            "configured"
        ]
        is False
    )


def test_open_table_reads_a_ready_register(client, db, world, google, publisher):
    connect(client, google, world.condo_a)
    drive.setup_registers(db, google, world.condo_a.id)
    table = drive.open_table(db, google, world.condo_a.id, RegisterKind.PEOPLE)
    table.append("p1", {"name": "Ana", "role": "Morador"})
    db.commit()
    assert [
        r.values["name"]
        for r in drive.open_table(db, google, world.condo_a.id, RegisterKind.PEOPLE).rows
    ] == ["Ana"]
    # Another condominium has nothing connected.
    try:
        drive.open_table(db, google, world.condo_b.id, RegisterKind.PEOPLE)
    except drive.RegisterUnavailable:
        pass
    else:
        raise AssertionError("condo_b has no Drive connection")
    assert (
        db.scalar(select(SheetRegister.status).where(SheetRegister.kind == RegisterKind.PEOPLE))
        == RegisterStatus.READY
    )
