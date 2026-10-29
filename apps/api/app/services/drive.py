"""Connecting a condominium to the manager's Google Drive and keeping its registers
(spreadsheets) in place. ADR 0010: the sheets are the record; Postgres only knows where
they are and holds the encrypted grant."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.jobs import JobPublisher
from app.integrations.google.base import (
    DRIVE_FILE_SCOPE,
    FOLDER_MIME,
    SPREADSHEET_MIME,
    Google,
    GoogleAuthError,
    GoogleError,
    GoogleNotFound,
    Workspace,
    folder_url,
    spreadsheet_url,
)
from app.models import Condominium, DriveConnection, SheetRegister, User
from app.models.enums import ActorType, DriveStatus, RegisterKind, RegisterStatus
from app.rbac.context import CondoContext, resolve_condo_role
from app.rbac.permissions import ORG_LEVEL_ROLES
from app.registers.specs import REGISTERS, RegisterSpec
from app.registers.table import SheetLayoutError, Table
from app.schemas.drive import DriveStatusOut, RegisterOut
from app.services import audit

logger = logging.getLogger(__name__)

DRIVE_SETUP_TOPIC = "drive-setup"
STATE_PURPOSE = "google-oauth"
STATE_TTL_SECONDS = 600

MSG_UNAVAILABLE = "O Google não respondeu. Tente sincronizar de novo em alguns minutos."
MSG_REAUTH = "O acesso ao Google Drive foi revogado ou expirou. Conecte o Drive de novo."
MSG_TAB_DELETED = 'A aba da planilha "{title}" foi apagada. Restaure-a pelo histórico de versões.'


class ConnectFailed(Exception):
    """Ends the OAuth callback. `code` goes back to the web app in the redirect URL."""

    def __init__(self, code: str, condominium_id: uuid.UUID | None = None):
        super().__init__(code)
        self.code = code
        self.condominium_id = condominium_id


class RegisterUnavailable(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _require_org_level(ctx: CondoContext) -> None:
    # The grant reaches the manager's own Drive: same bar as configuring WhatsApp.
    if not ctx.is_org_level:
        raise Forbidden("Only organization admins can connect Google Drive")


def _connection(db: Session, condominium_id: uuid.UUID) -> DriveConnection | None:
    return db.scalar(
        select(DriveConnection).where(DriveConnection.condominium_id == condominium_id)
    )


def _registers(db: Session, condominium_id: uuid.UUID) -> dict[RegisterKind, SheetRegister]:
    rows = db.scalars(
        select(SheetRegister).where(SheetRegister.condominium_id == condominium_id)
    ).all()
    return {r.kind: r for r in rows}


def lock_sheets(db: Session, condominium_id: uuid.UUID) -> None:
    """Serializes sheet writes for one condominium until the transaction ends, so two
    workers can't both read "no row with this ID" and append it twice."""
    key = db.scalar(select(func.hashtextextended(f"sheets:{condominium_id}", 0)))
    db.execute(select(func.pg_advisory_xact_lock(key)))


# Connect flow


def start_connect(ctx: CondoContext, google: Google) -> str:
    _require_org_level(ctx)
    if not google.configured:
        raise Conflict("Google Drive is not configured on this server")
    state = crypto.sign(
        {"c": str(ctx.condominium_id), "u": str(ctx.user.id)},
        purpose=STATE_PURPOSE,
        ttl_seconds=STATE_TTL_SECONDS,
    )
    return google.authorization_url(state)


def complete_connect(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> uuid.UUID:
    try:
        payload = crypto.verify(state or "", purpose=STATE_PURPOSE)
        condominium_id = uuid.UUID(payload["c"])
        user_id = uuid.UUID(payload["u"])
    except (crypto.InvalidSignedToken, KeyError, ValueError) as exc:
        raise ConnectFailed("invalid_state") from exc
    if error or not code:
        raise ConnectFailed("denied", condominium_id)

    # Re-check access: the state was signed up to ten minutes ago.
    user = db.get(User, user_id)
    condo = db.get(Condominium, condominium_id)
    role = resolve_condo_role(db, user, condo) if user and condo else None
    if role not in ORG_LEVEL_ROLES:
        raise ConnectFailed("forbidden", condominium_id)

    try:
        grant = google.exchange_code(code)
    except GoogleAuthError as exc:
        raise ConnectFailed("google_refused", condominium_id) from exc
    except GoogleError as exc:
        raise ConnectFailed("google_unavailable", condominium_id) from exc
    if DRIVE_FILE_SCOPE not in grant.scopes:
        # The manager unticked Drive access on the consent screen.
        google.revoke(grant.refresh_token)
        raise ConnectFailed("scope_missing", condominium_id)

    now = datetime.now(timezone.utc)
    connection = _connection(db, condominium_id)
    account_changed = connection is not None and connection.account_email != grant.email
    if connection is None:
        connection = DriveConnection(condominium_id=condominium_id)
        db.add(connection)
    elif account_changed:
        # Sheets in the old account are out of reach of the new grant. Revoking the old
        # grant is safe only here: for the same account it would also kill the new one.
        try:
            google.revoke(crypto.decrypt_secret(connection.refresh_token_encrypted))
        except ValueError:
            logger.warning("previous drive grant unreadable; not revoked")
        for register in _registers(db, condominium_id).values():
            db.delete(register)
        connection.folder_id = None
        db.flush()
    connection.provider = "google"
    connection.account_email = grant.email[:320]
    connection.refresh_token_encrypted = crypto.encrypt_secret(grant.refresh_token)
    connection.scopes = " ".join(sorted(grant.scopes))[:500]
    connection.status = DriveStatus.ACTIVE
    connection.connected_by_user_id = user_id
    connection.connected_at = now
    db.flush()
    _mark_pending(db, connection)

    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condominium_id,
        actor_type=ActorType.USER,
        actor_id=user_id,
        action="drive.connected",
        entity_type="drive_connection",
        entity_id=connection.id,
        data={"provider": "google", "account_changed": account_changed},
    )
    db.commit()
    publisher.publish(DRIVE_SETUP_TOPIC, {"condominium_id": str(condominium_id)})
    return condominium_id


def _mark_pending(db: Session, connection: DriveConnection) -> None:
    existing = _registers(db, connection.condominium_id)
    for kind in REGISTERS:
        register = existing.get(kind)
        if register is None:
            register = SheetRegister(
                condominium_id=connection.condominium_id,
                connection_id=connection.id,
                kind=kind,
            )
            db.add(register)
        register.status = RegisterStatus.PENDING
        register.last_error = None
    db.flush()


def status(db: Session, ctx: CondoContext, google: Google) -> DriveStatusOut:
    connection = _connection(db, ctx.condominium_id)
    if connection is None:
        return DriveStatusOut(configured=google.configured, connected=False)
    registers = _registers(db, ctx.condominium_id)
    return DriveStatusOut(
        configured=google.configured,
        connected=True,
        status=connection.status,
        account_email=connection.account_email,
        connected_at=connection.connected_at,
        folder_url=folder_url(connection.folder_id) if connection.folder_id else None,
        registers=[
            RegisterOut(
                kind=kind,
                title=spec.title,
                status=registers[kind].status if kind in registers else RegisterStatus.PENDING,
                url=(
                    spreadsheet_url(registers[kind].spreadsheet_id)
                    if kind in registers and registers[kind].spreadsheet_id
                    else None
                ),
                last_error=registers[kind].last_error if kind in registers else None,
            )
            for kind, spec in REGISTERS.items()
        ],
    )


def request_sync(db: Session, ctx: CondoContext, publisher: JobPublisher) -> None:
    _require_org_level(ctx)
    connection = _connection(db, ctx.condominium_id)
    if connection is None:
        raise NotFound("Google Drive is not connected")
    if connection.status == DriveStatus.REAUTH_REQUIRED:
        raise Conflict("Reconnect Google Drive first")
    _mark_pending(db, connection)
    audit.record_user_action(db, ctx, "drive.sync_requested", "drive_connection", connection.id)
    db.commit()
    publisher.publish(DRIVE_SETUP_TOPIC, {"condominium_id": str(ctx.condominium_id)})


def disconnect(db: Session, ctx: CondoContext, google: Google) -> None:
    _require_org_level(ctx)
    connection = _connection(db, ctx.condominium_id)
    if connection is None:
        raise NotFound("Google Drive is not connected")
    try:
        google.revoke(crypto.decrypt_secret(connection.refresh_token_encrypted))
    except ValueError:
        logger.warning("stored drive grant unreadable; disconnecting without revoking")
    audit.record_user_action(db, ctx, "drive.disconnected", "drive_connection", connection.id)
    db.delete(connection)  # registers cascade; the spreadsheets stay in the Drive
    db.commit()


# Worker


def setup_registers(db: Session, google: Google, condominium_id: uuid.UUID) -> None:
    """Finds or creates the condominium's folder and spreadsheets. Safe to re-run: files
    are found again by their appProperties, so nothing is created twice."""
    connection = _connection(db, condominium_id)
    condo = db.get(Condominium, condominium_id)
    if connection is None or condo is None or connection.status != DriveStatus.ACTIVE:
        return
    lock_sheets(db, condominium_id)
    _mark_pending(db, connection)
    registers = _registers(db, condominium_id)

    try:
        workspace = _workspace(google, connection)
        folder_id = _ensure_folder(workspace, connection, condo)
        for kind, spec in REGISTERS.items():
            register = registers[kind]
            try:
                _ensure_register(workspace, folder_id, condo, register, spec)
                register.status, register.last_error = RegisterStatus.READY, None
            except SheetLayoutError as exc:
                register.status, register.last_error = RegisterStatus.FAILED, exc.message
            except GoogleAuthError:
                raise
            except GoogleError:
                logger.warning("register setup failed", extra={"register": str(kind)})
                register.status, register.last_error = RegisterStatus.FAILED, MSG_UNAVAILABLE
    except GoogleAuthError:
        connection.status = DriveStatus.REAUTH_REQUIRED
        _fail_all(registers, MSG_REAUTH)
    except GoogleError:
        logger.warning("drive folder setup failed", extra={"condominium_id": str(condo.id)})
        _fail_all(registers, MSG_UNAVAILABLE)

    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="drive.registers_synced",
        entity_type="drive_connection",
        entity_id=connection.id,
        data={
            "ready": sorted(k for k, r in registers.items() if r.status == RegisterStatus.READY),
            "failed": sorted(k for k, r in registers.items() if r.status == RegisterStatus.FAILED),
        },
    )
    db.commit()


def _workspace(google: Google, connection: DriveConnection) -> Workspace:
    try:
        refresh_token = crypto.decrypt_secret(connection.refresh_token_encrypted)
    except ValueError as exc:
        # SECRET_KEY changed since the grant was stored: only a reconnect recovers.
        raise GoogleAuthError("Stored grant is unreadable") from exc
    return google.workspace(refresh_token)


def _fail_all(registers: dict[RegisterKind, SheetRegister], message: str) -> None:
    for register in registers.values():
        if register.status != RegisterStatus.READY:
            register.status, register.last_error = RegisterStatus.FAILED, message


def _props(condo: Condominium, item: str) -> dict[str, str]:
    return {"zela_condominium": str(condo.id), "zela_item": item}


def _ensure_folder(ws: Workspace, connection: DriveConnection, condo: Condominium) -> str:
    if connection.folder_id and ws.is_available(connection.folder_id):
        return connection.folder_id
    props = _props(condo, "folder")
    folder_id = ws.find_file(props, mime_type=FOLDER_MIME) or ws.create_folder(
        f"Zela · {condo.name}", app_properties=props
    )
    connection.folder_id = folder_id
    return folder_id


def _ensure_register(
    ws: Workspace,
    folder_id: str,
    condo: Condominium,
    register: SheetRegister,
    spec: RegisterSpec,
) -> None:
    if not (register.spreadsheet_id and ws.is_available(register.spreadsheet_id)):
        props = _props(condo, str(spec.kind))
        found = ws.find_file(props, mime_type=SPREADSHEET_MIME)
        if found:
            # Zela creates each register with a single tab, and the first tab is ID 0.
            register.spreadsheet_id, register.sheet_id = found, 0
        else:
            ref = ws.create_spreadsheet(
                spec.title,
                folder_id=folder_id,
                tab_title=spec.title,
                headers=spec.headers,
                choices=spec.choices,
                app_properties=props,
            )
            register.spreadsheet_id, register.sheet_id = ref.spreadsheet_id, ref.sheet_id
    try:
        # Validates the header and adds columns introduced since the sheet was created.
        Table(ws, register.spreadsheet_id, register.sheet_id, spec).load()
    except GoogleNotFound as exc:
        raise SheetLayoutError(MSG_TAB_DELETED.format(title=spec.title)) from exc


def open_table(db: Session, google: Google, condominium_id: uuid.UUID, kind: RegisterKind) -> Table:
    """Loads one register under the condominium's sheet lock. The caller commits (which
    releases the lock) after its last write."""
    connection = _connection(db, condominium_id)
    register = _registers(db, condominium_id).get(kind)
    if connection is None:
        raise RegisterUnavailable("Google Drive is not connected")
    if connection.status != DriveStatus.ACTIVE:
        raise RegisterUnavailable(MSG_REAUTH)
    if register is None or register.spreadsheet_id is None or register.sheet_id is None:
        raise RegisterUnavailable("The register has not been created yet")
    lock_sheets(db, condominium_id)
    try:
        workspace = _workspace(google, connection)
        return Table(workspace, register.spreadsheet_id, register.sheet_id, REGISTERS[kind]).load()
    except GoogleAuthError as exc:
        connection.status = DriveStatus.REAUTH_REQUIRED
        db.commit()
        raise RegisterUnavailable(MSG_REAUTH) from exc
    except SheetLayoutError as exc:
        raise RegisterUnavailable(exc.message) from exc
    except GoogleNotFound as exc:
        raise RegisterUnavailable(MSG_TAB_DELETED.format(title=REGISTERS[kind].title)) from exc
