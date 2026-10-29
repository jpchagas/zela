"""In-memory Google Drive with the same contract as GoogleClient. Tests use it to inspect
and hand-edit spreadsheets; GOOGLE_MODE=fake lets the connect flow run locally without
OAuth credentials (contents are lost when the process restarts)."""

import itertools
from dataclasses import dataclass, field
from urllib.parse import urlencode

from app.integrations.google.base import (
    DRIVE_FILE_SCOPE,
    FOLDER_MIME,
    SCOPES,
    SPREADSHEET_MIME,
    Cell,
    GoogleAuthError,
    GoogleNotFound,
    Grant,
    SpreadsheetRef,
)


@dataclass
class FakeTab:
    title: str
    rows: list[list[str]] = field(default_factory=list)
    header_protected: bool = False
    choices: dict[int, list[str]] = field(default_factory=dict)


@dataclass
class FakeFile:
    id: str
    owner: str
    name: str
    mime_type: str
    parents: list[str]
    app_properties: dict[str, str]
    trashed: bool = False
    tabs: dict[int, FakeTab] = field(default_factory=dict)


class FakeGoogle:
    def __init__(self, redirect_uri: str = "http://testserver/oauth/google/callback"):
        self.redirect_uri = redirect_uri
        self.files: dict[str, FakeFile] = {}
        self.revoked: set[str] = set()
        self._codes: dict[str, Grant] = {}
        self._accounts: dict[str, Grant] = {}
        self._ids = itertools.count(1)

    @property
    def configured(self) -> bool:
        return True

    def issue_code(
        self, email: str = "sindico@example.com", scopes: tuple[str, ...] = SCOPES
    ) -> str:
        """What Google's consent screen would hand back to the callback."""
        code = f"code-{next(self._ids)}"
        self._codes[code] = Grant(
            refresh_token=f"refresh-{code}", email=email, scopes=frozenset(scopes)
        )
        return code

    def authorization_url(self, state: str) -> str:
        # Skips the consent screen: straight back to the callback with a fresh code.
        return f"{self.redirect_uri}?{urlencode({'code': self.issue_code(), 'state': state})}"

    def exchange_code(self, code: str) -> Grant:
        grant = self._codes.pop(code, None)
        if grant is None:
            raise GoogleAuthError("invalid_grant")
        self._accounts[grant.refresh_token] = grant
        return grant

    def revoke(self, refresh_token: str) -> None:
        self.revoked.add(refresh_token)

    def workspace(self, refresh_token: str) -> "FakeWorkspace":
        return FakeWorkspace(self, refresh_token)

    # Test helpers

    def files_of(self, email: str, mime_type: str | None = None) -> list[FakeFile]:
        return [
            f
            for f in self.files.values()
            if f.owner == email and (mime_type is None or f.mime_type == mime_type)
        ]

    def tab(self, spreadsheet_id: str, sheet_id: int = 0) -> FakeTab:
        return self.files[spreadsheet_id].tabs[sheet_id]


class FakeWorkspace:
    def __init__(self, google: FakeGoogle, refresh_token: str):
        self._google = google
        self._token = refresh_token

    @property
    def _owner(self) -> str:
        grant = self._google._accounts.get(self._token)
        if grant is None or self._token in self._google.revoked:
            raise GoogleAuthError("invalid_grant")
        if DRIVE_FILE_SCOPE not in grant.scopes:
            raise GoogleAuthError("insufficient scope")
        return grant.email

    def _file(self, file_id: str) -> FakeFile:
        found = self._google.files.get(file_id)
        if found is None or found.owner != self._owner:
            raise GoogleNotFound("File not found")
        return found

    def _tab(self, spreadsheet_id: str, sheet_id: int) -> FakeTab:
        tab = self._file(spreadsheet_id).tabs.get(sheet_id)
        if tab is None:
            raise GoogleNotFound("The register's tab was deleted")
        return tab

    def find_file(self, app_properties: dict[str, str], *, mime_type: str) -> str | None:
        owner = self._owner
        for f in self._google.files.values():
            if (
                f.owner == owner
                and f.mime_type == mime_type
                and not f.trashed
                and app_properties.items() <= f.app_properties.items()
            ):
                return f.id
        return None

    def is_available(self, file_id: str) -> bool:
        try:
            return not self._file(file_id).trashed
        except GoogleNotFound:
            return False

    def _create(self, name: str, mime_type: str, parents: list[str], props: dict[str, str]):
        file = FakeFile(
            id=f"file-{next(self._google._ids)}",
            owner=self._owner,
            name=name,
            mime_type=mime_type,
            parents=parents,
            app_properties=dict(props),
        )
        self._google.files[file.id] = file
        return file

    def create_folder(self, name: str, *, app_properties: dict[str, str]) -> str:
        return self._create(name, FOLDER_MIME, [], app_properties).id

    def create_spreadsheet(
        self,
        name: str,
        *,
        folder_id: str,
        tab_title: str,
        headers: list[str],
        choices: dict[int, list[str]],
        app_properties: dict[str, str],
    ) -> SpreadsheetRef:
        file = self._create(name, SPREADSHEET_MIME, [folder_id], app_properties)
        file.tabs[0] = FakeTab(
            title=tab_title, rows=[list(headers)], header_protected=True, choices=dict(choices)
        )
        return SpreadsheetRef(spreadsheet_id=file.id, sheet_id=0)

    def read_values(self, spreadsheet_id: str, sheet_id: int) -> list[list[str]]:
        rows = [list(r) for r in self._tab(spreadsheet_id, sheet_id).rows]
        # Like the Sheets API: trailing empty cells and rows are not returned.
        for row in rows:
            while row and row[-1] == "":
                row.pop()
        while rows and not rows[-1]:
            rows.pop()
        return rows

    def append_row(self, spreadsheet_id: str, sheet_id: int, values: list[str]) -> int:
        tab = self._tab(spreadsheet_id, sheet_id)
        used = len(self.read_values(spreadsheet_id, sheet_id))
        del tab.rows[used:]
        tab.rows.append(list(values))
        return len(tab.rows)

    def update_cells(self, spreadsheet_id: str, sheet_id: int, cells: list[Cell]) -> None:
        tab = self._tab(spreadsheet_id, sheet_id)
        for cell in cells:
            while len(tab.rows) < cell.row:
                tab.rows.append([])
            row = tab.rows[cell.row - 1]
            while len(row) <= cell.col:
                row.append("")
            row[cell.col] = cell.value
