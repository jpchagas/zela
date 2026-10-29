"""Google OAuth, Drive v3 and Sheets v4 over plain HTTPS (no Google SDK: two small APIs
don't justify its size)."""

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx

from app.integrations.google.base import (
    FOLDER_MIME,
    SCOPES,
    SPREADSHEET_MIME,
    Cell,
    GoogleAuthError,
    GoogleError,
    GoogleNotFound,
    Grant,
    SpreadsheetRef,
)

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE = "https://www.googleapis.com/drive/v3/files"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"

RETRY_STATUSES = {429, 500, 502, 503, 504}
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
MAX_ATTEMPTS = 3

HEADER_NOTE = "Cabeçalho do Zela: não renomeie as colunas."


class GoogleClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http or httpx.Client(timeout=20.0)
        self._sleep = sleep

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            # offline + consent: Google returns a refresh token on every connect.
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> Grant:
        data = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
            }
        )
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise GoogleAuthError("Google did not return a refresh token")
        return Grant(
            refresh_token=refresh_token,
            email=_id_token_email(data.get("id_token", "")),
            scopes=frozenset(data.get("scope", "").split()),
        )

    def refresh(self, refresh_token: str) -> str:
        data = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        return data["access_token"]

    def revoke(self, refresh_token: str) -> None:
        try:
            self._http.post(REVOKE_URL, data={"token": refresh_token})
        except httpx.HTTPError:
            logger.warning("google token revoke failed")

    def workspace(self, refresh_token: str) -> "GoogleWorkspace":
        return GoogleWorkspace(self, refresh_token)

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        form = {**form, "client_id": self._client_id, "client_secret": self._client_secret}
        try:
            response = self._http.post(TOKEN_URL, data=form)
        except httpx.HTTPError as exc:
            raise GoogleError(f"Google token endpoint unreachable: {type(exc).__name__}") from exc
        if response.status_code == 200:
            return response.json()
        error = _json(response).get("error", "")
        if error in ("invalid_grant", "unauthorized_client", "invalid_client"):
            raise GoogleAuthError(f"Google refused the grant: {error}")
        raise GoogleError(f"Google token endpoint returned {response.status_code}")


class GoogleWorkspace:
    def __init__(self, google: GoogleClient, refresh_token: str):
        self._google = google
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._tab_titles: dict[tuple[str, int], str] = {}

    # Drive

    def find_file(self, app_properties: dict[str, str], *, mime_type: str) -> str | None:
        clauses = [f"mimeType = '{mime_type}'", "trashed = false"]
        clauses += [
            f"appProperties has {{ key='{_q(k)}' and value='{_q(v)}' }}"
            for k, v in sorted(app_properties.items())
        ]
        data = self._call(
            "GET",
            DRIVE,
            params={"q": " and ".join(clauses), "fields": "files(id)", "pageSize": 1},
        )
        files = data.get("files", [])
        return files[0]["id"] if files else None

    def is_available(self, file_id: str) -> bool:
        try:
            data = self._call("GET", f"{DRIVE}/{file_id}", params={"fields": "id,trashed"})
        except GoogleNotFound:
            return False
        return not data.get("trashed", False)

    def create_folder(self, name: str, *, app_properties: dict[str, str]) -> str:
        body = {"name": name, "mimeType": FOLDER_MIME, "appProperties": app_properties}
        return self._call("POST", DRIVE, params={"fields": "id"}, json=body)["id"]

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
        body = {
            "name": name,
            "mimeType": SPREADSHEET_MIME,
            "parents": [folder_id],
            "appProperties": app_properties,
        }
        spreadsheet_id = self._call("POST", DRIVE, params={"fields": "id"}, json=body)["id"]
        sheet_id = self._sheet_props(spreadsheet_id)[0]["sheetId"]
        requests: list[dict[str, Any]] = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "title": tab_title,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "title,gridProperties.frozenRowCount",
                }
            },
            {
                "updateCells": {
                    "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                    "rows": [
                        {
                            "values": [
                                {
                                    "userEnteredValue": {"stringValue": h},
                                    "userEnteredFormat": {"textFormat": {"bold": True}},
                                }
                                for h in headers
                            ]
                        }
                    ],
                    "fields": "userEnteredValue,userEnteredFormat.textFormat.bold",
                }
            },
            {
                # Warning-only: the manager owns the file and may still edit it.
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "description": HEADER_NOTE,
                        "warningOnly": True,
                    }
                }
            },
        ]
        for col, values in sorted(choices.items()):
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": col,
                            "endColumnIndex": col + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": v} for v in values],
                            },
                            # Hand-typed values outside the list are allowed, only flagged.
                            "strict": False,
                            "showCustomUi": True,
                        },
                    }
                }
            )
        self._call("POST", f"{SHEETS}/{spreadsheet_id}:batchUpdate", json={"requests": requests})
        self._tab_titles[(spreadsheet_id, sheet_id)] = tab_title
        return SpreadsheetRef(spreadsheet_id=spreadsheet_id, sheet_id=sheet_id)

    # Sheets values

    def read_values(self, spreadsheet_id: str, sheet_id: int) -> list[list[str]]:
        tab = self._a1_tab(spreadsheet_id, sheet_id)
        data = self._call(
            "GET",
            f"{SHEETS}/{spreadsheet_id}/values/{tab}",
            params={"valueRenderOption": "FORMATTED_VALUE", "majorDimension": "ROWS"},
        )
        return [[str(v) for v in row] for row in data.get("values", [])]

    def append_row(self, spreadsheet_id: str, sheet_id: int, values: list[str]) -> int:
        tab = self._a1_tab(spreadsheet_id, sheet_id)
        data = self._call(
            "POST",
            f"{SHEETS}/{spreadsheet_id}/values/{tab}!A1:append",
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"values": [values]},
        )
        match = re.search(r"!\$?[A-Z]+\$?(\d+)", data.get("updates", {}).get("updatedRange", ""))
        if not match:
            raise GoogleError("Sheets append did not report the row it wrote")
        return int(match.group(1))

    def update_cells(self, spreadsheet_id: str, sheet_id: int, cells: list[Cell]) -> None:
        if not cells:
            return
        tab = self._a1_tab(spreadsheet_id, sheet_id)
        body = {
            "valueInputOption": "RAW",
            "data": [
                {"range": f"{tab}!{column_letter(c.col)}{c.row}", "values": [[c.value]]}
                for c in cells
            ],
        }
        self._call("POST", f"{SHEETS}/{spreadsheet_id}/values:batchUpdate", json=body)

    # Plumbing

    def _sheet_props(self, spreadsheet_id: str) -> list[dict[str, Any]]:
        data = self._call(
            "GET",
            f"{SHEETS}/{spreadsheet_id}",
            params={"fields": "sheets.properties(sheetId,title)"},
        )
        return [s["properties"] for s in data.get("sheets", [])]

    def _a1_tab(self, spreadsheet_id: str, sheet_id: int) -> str:
        # Tabs are tracked by ID, so the manager may rename them; A1 ranges need the title.
        key = (spreadsheet_id, sheet_id)
        if key not in self._tab_titles:
            for props in self._sheet_props(spreadsheet_id):
                self._tab_titles[(spreadsheet_id, props["sheetId"])] = props["title"]
        if key not in self._tab_titles:
            raise GoogleNotFound("The register's tab was deleted")
        return "'" + self._tab_titles[key].replace("'", "''") + "'"

    def _call(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        refreshed = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._access_token is None:
                self._access_token = self._google.refresh(self._refresh_token)
            headers = {"Authorization": f"Bearer {self._access_token}"}
            try:
                response = self._google._http.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise GoogleError(f"Google unreachable: {type(exc).__name__}") from exc
                self._google._sleep(2 ** (attempt - 1))
                continue
            status = response.status_code
            if status < 300:
                return response.json() if response.content else {}
            if status == 401 and not refreshed:
                self._access_token, refreshed = None, True
                continue
            if status == 401:
                raise GoogleAuthError("Google rejected the access token")
            if status == 404:
                raise GoogleNotFound("File not found")
            if (status in RETRY_STATUSES or _rate_limited(response)) and attempt < MAX_ATTEMPTS:
                self._google._sleep(2 ** (attempt - 1))
                continue
            if status == 403 and _api_disabled(response):
                # A setup problem on our side (Drive/Sheets API not enabled), not the grant.
                logger.error("google api not enabled for the oauth client's project")
                raise GoogleError("Google API not enabled for this project")
            if status == 403 and not _rate_limited(response):
                raise GoogleAuthError(f"Google denied access: {_reason(response)}")
            raise GoogleError(f"Google API returned {status}: {_reason(response)}")
        raise GoogleError("Google API retries exhausted")


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _reason(response: httpx.Response) -> str:
    error = _json(response).get("error", {})
    if isinstance(error, dict):
        reasons = [e.get("reason", "") for e in error.get("errors", [])]
        return ",".join(r for r in reasons if r) or str(error.get("status", ""))[:80]
    return str(error)[:80]


def _rate_limited(response: httpx.Response) -> bool:
    return response.status_code == 403 and _reason(response) in RATE_LIMIT_REASONS


def _api_disabled(response: httpx.Response) -> bool:
    return _reason(response) == "accessNotConfigured" or "SERVICE_DISABLED" in response.text


def _id_token_email(id_token: str) -> str:
    # Received directly from Google's token endpoint over TLS, so the claims need no
    # signature check here (Google's OpenID Connect guidance).
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return ""
    return str(claims.get("email", ""))
