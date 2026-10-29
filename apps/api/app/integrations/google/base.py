"""Contract for the manager's Google Drive. `GoogleClient` talks to Google; `FakeGoogle`
(app.integrations.google.fake) is an in-memory Drive for tests and local runs."""

from dataclasses import dataclass
from typing import Protocol

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
# drive.file only reaches files Zela created (or the manager picks), and is a
# non-sensitive scope, so no paid Google security assessment (ADR 0010).
SCOPES = ("openid", "email", DRIVE_FILE_SCOPE)

FOLDER_MIME = "application/vnd.google-apps.folder"
SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"


class GoogleError(Exception):
    """A Google call failed; retrying later may work."""


class GoogleAuthError(GoogleError):
    """The stored grant is no longer valid (revoked, expired, or missing scope)."""


class GoogleNotFound(GoogleError):
    pass


@dataclass(frozen=True)
class Grant:
    refresh_token: str
    email: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class SpreadsheetRef:
    spreadsheet_id: str
    sheet_id: int


@dataclass(frozen=True)
class Cell:
    row: int  # 1-based, as people see it in the sheet
    col: int  # 0-based
    value: str


def spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


class Workspace(Protocol):
    """Drive and Sheets operations as one Google account. Values are written RAW, so
    text that looks like a formula stays text."""

    def find_file(self, app_properties: dict[str, str], *, mime_type: str) -> str | None: ...

    def is_available(self, file_id: str) -> bool: ...

    def create_folder(self, name: str, *, app_properties: dict[str, str]) -> str: ...

    def upload_file(
        self,
        name: str,
        *,
        mime_type: str,
        data: bytes,
        folder_id: str,
        app_properties: dict[str, str],
    ) -> str: ...

    def download_file(self, file_id: str) -> bytes: ...

    def create_spreadsheet(
        self,
        name: str,
        *,
        folder_id: str,
        tab_title: str,
        headers: list[str],
        choices: dict[int, list[str]],
        app_properties: dict[str, str],
    ) -> SpreadsheetRef: ...

    def read_values(self, spreadsheet_id: str, sheet_id: int) -> list[list[str]]: ...

    def append_row(self, spreadsheet_id: str, sheet_id: int, values: list[str]) -> int:
        """Adds a row after the data and returns its row number."""
        ...

    def update_cells(self, spreadsheet_id: str, sheet_id: int, cells: list[Cell]) -> None: ...


class Google(Protocol):
    @property
    def configured(self) -> bool: ...

    def authorization_url(self, state: str) -> str: ...

    def exchange_code(self, code: str) -> Grant: ...

    def revoke(self, refresh_token: str) -> None: ...

    def workspace(self, refresh_token: str) -> Workspace: ...
