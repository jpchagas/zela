"""Helpers for sheet-backed condominiums (ADR 0010/0011) in tests."""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.google.fake import FakeGoogle, FakeTab
from app.models import Condominium, SheetRegister
from app.models.enums import RegisterKind
from app.registers.specs import REGISTERS
from app.services import drive
from tests.factories import auth

MANAGER_PHONE = "+5511955550000"


def connect_drive(client, db: Session, google: FakeGoogle, condo: Condominium, owner_email: str):
    """Connects the condominium's Drive (fake) and creates its registers."""
    response = client.post(f"/v1/condominiums/{condo.id}/drive/connect", headers=auth(owner_email))
    state = parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]
    redirect = client.get(
        "/oauth/google/callback",
        params={"code": google.issue_code(), "state": state},
        follow_redirects=False,
    )
    assert redirect.status_code == 303
    drive.setup_registers(db, google, condo.id)


def tab(db: Session, google: FakeGoogle, condo: Condominium, kind=RegisterKind.PEOPLE) -> FakeTab:
    register = db.scalar(
        select(SheetRegister).where(
            SheetRegister.condominium_id == condo.id, SheetRegister.kind == kind
        )
    )
    return google.tab(register.spreadsheet_id, register.sheet_id)


def add_row(sheet: FakeTab, kind=RegisterKind.PEOPLE, **values: str) -> None:
    """Types a row into the sheet by hand, as the manager would."""
    spec = REGISTERS[kind]
    header = sheet.rows[0]
    row = [""] * len(header)
    for key, value in values.items():
        row[header.index(spec.column(key).header)] = value
    sheet.rows.append(row)


def row_dict(sheet: FakeTab, number: int, kind=RegisterKind.PEOPLE) -> dict[str, str]:
    spec = REGISTERS[kind]
    header, row = sheet.rows[0], sheet.rows[number - 1]
    return {
        c.key: (row[header.index(c.header)] if header.index(c.header) < len(row) else "")
        for c in spec.columns
    }


def confirm_manager(db: Session, condo: Condominium, phone: str = MANAGER_PHONE) -> None:
    now = datetime.now(timezone.utc)
    condo.manager_phone_e164 = phone
    condo.manager_phone_requested_at = now
    condo.manager_phone_confirmed_at = now
    db.commit()
