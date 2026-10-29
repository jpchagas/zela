"""GoogleClient's requests and error handling, against a mock transport (no network)."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.integrations.google.base import DRIVE_FILE_SCOPE, Cell, GoogleAuthError, GoogleError
from app.integrations.google.client import GoogleClient, column_letter


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


class Google:
    """Scripted Google endpoints; records every request."""

    def __init__(self, routes):
        self.routes = routes  # list of (method, url-substring, response or callable)
        self.requests: list[httpx.Request] = []
        self.slept: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for i, (method, fragment, response) in enumerate(self.routes):
            if request.method == method and fragment in str(request.url):
                self.routes.pop(i)
                return response(request) if callable(response) else response
        raise AssertionError(f"unexpected {request.method} {request.url}")

    def client(self) -> GoogleClient:
        return GoogleClient(
            client_id="cid",
            client_secret="secret",
            redirect_uri="http://localhost:8000/oauth/google/callback",
            http=httpx.Client(transport=httpx.MockTransport(self.handler)),
            sleep=self.slept.append,
        )


TOKEN = ("POST", "oauth2.googleapis.com/token", httpx.Response(200, json={"access_token": "at"}))
TABS = (
    "GET",
    "/spreadsheets/s1?fields",
    httpx.Response(200, json={"sheets": [{"properties": {"sheetId": 7, "title": "D'Ávila"}}]}),
)


def test_authorization_url_asks_for_offline_drive_file_access():
    url = Google([]).client().authorization_url("st")
    query = parse_qs(urlparse(url).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert DRIVE_FILE_SCOPE in query["scope"][0].split()
    assert query["state"] == ["st"]
    assert "drive " not in query["scope"][0] + " "  # never the full-Drive scope


def test_exchange_code_reads_the_grant():
    body = {
        "refresh_token": "rt",
        "access_token": "at",
        "scope": f"openid email {DRIVE_FILE_SCOPE}",
        "id_token": _id_token("sindico@example.com"),
    }
    google = Google([("POST", "/token", httpx.Response(200, json=body))])
    grant = google.client().exchange_code("abc")
    assert grant.refresh_token == "rt" and grant.email == "sindico@example.com"
    assert DRIVE_FILE_SCOPE in grant.scopes
    form = parse_qs(google.requests[0].content.decode())
    assert form["grant_type"] == ["authorization_code"] and form["code"] == ["abc"]


def test_exchange_code_errors():
    no_refresh = Google([("POST", "/token", httpx.Response(200, json={"access_token": "at"}))])
    with pytest.raises(GoogleAuthError):
        no_refresh.client().exchange_code("abc")
    refused = Google([("POST", "/token", httpx.Response(400, json={"error": "invalid_grant"}))])
    with pytest.raises(GoogleAuthError):
        refused.client().exchange_code("abc")


def test_append_is_raw_and_reports_the_row():
    append = (
        "POST",
        ":append",
        httpx.Response(200, json={"updates": {"updatedRange": "'D''Ávila'!A12:C12"}}),
    )
    google = Google([TOKEN, TABS, append])
    row = google.client().workspace("rt").append_row("s1", 7, ["=HYPERLINK(1)", "b"])
    assert row == 12
    request = google.requests[-1]
    assert request.url.params["valueInputOption"] == "RAW"
    # The tab is found by ID and its title quoted for A1 notation.
    assert "'D''Ávila'!A1:append" in httpx.URL(str(request.url)).path
    assert json.loads(request.content) == {"values": [["=HYPERLINK(1)", "b"]]}


def test_update_cells_uses_a1_ranges():
    update = ("POST", "values:batchUpdate", httpx.Response(200, json={}))
    google = Google([TOKEN, TABS, update])
    google.client().workspace("rt").update_cells("s1", 7, [Cell(3, 0, "x"), Cell(3, 27, "y")])
    body = json.loads(google.requests[-1].content)
    assert body["valueInputOption"] == "RAW"
    assert [d["range"] for d in body["data"]] == ["'D''Ávila'!A3", "'D''Ávila'!AB3"]


def test_an_expired_access_token_is_refreshed_once():
    google = Google(
        [
            TOKEN,
            ("GET", "/files/f1", httpx.Response(401)),
            TOKEN,
            ("GET", "/files/f1", httpx.Response(200, json={"id": "f1", "trashed": False})),
        ]
    )
    assert google.client().workspace("rt").is_available("f1") is True
    assert sum("/token" in str(r.url) for r in google.requests) == 2


def test_rate_limits_and_server_errors_are_retried_with_backoff():
    limited = httpx.Response(403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}})
    google = Google(
        [
            TOKEN,
            ("GET", "/files/f1", limited),
            ("GET", "/files/f1", httpx.Response(503)),
            ("GET", "/files/f1", httpx.Response(200, json={"id": "f1", "trashed": True})),
        ]
    )
    assert google.client().workspace("rt").is_available("f1") is False  # trashed
    assert google.slept == [1, 2]


def test_permission_errors_and_missing_files():
    denied = httpx.Response(
        403, json={"error": {"errors": [{"reason": "insufficientPermissions"}]}}
    )
    google = Google(
        [TOKEN, ("GET", "/files/f1", denied), ("GET", "/files/f2", httpx.Response(404))]
    )
    ws = google.client().workspace("rt")
    with pytest.raises(GoogleAuthError):
        ws.is_available("f1")
    assert ws.is_available("f2") is False


def test_a_disabled_api_is_a_setup_error_not_a_revoked_grant():
    disabled = httpx.Response(
        403,
        json={
            "error": {"errors": [{"reason": "accessNotConfigured"}], "status": "PERMISSION_DENIED"}
        },
    )
    google = Google([TOKEN, ("GET", "/files/f1", disabled)])
    with pytest.raises(GoogleError) as info:
        google.client().workspace("rt").is_available("f1")
    assert not isinstance(info.value, GoogleAuthError)


def test_persistent_server_errors_give_up():
    google = Google([TOKEN] + [("GET", "/files/f1", httpx.Response(500))] * 3)
    with pytest.raises(GoogleError):
        google.client().workspace("rt").is_available("f1")


def test_create_spreadsheet_protects_the_header_and_adds_dropdowns():
    google = Google(
        [
            TOKEN,
            ("POST", "/drive/v3/files", httpx.Response(200, json={"id": "s9"})),
            (
                "GET",
                "/spreadsheets/s9?fields",
                httpx.Response(
                    200, json={"sheets": [{"properties": {"sheetId": 0, "title": "Página1"}}]}
                ),
            ),
            ("POST", "s9:batchUpdate", httpx.Response(200, json={})),
        ]
    )
    ref = (
        google.client()
        .workspace("rt")
        .create_spreadsheet(
            "Pessoas",
            folder_id="fold",
            tab_title="Pessoas",
            headers=["ID Zela", "Papel"],
            choices={1: ["Síndico", "Morador"]},
            app_properties={"zela_item": "people"},
        )
    )
    assert (ref.spreadsheet_id, ref.sheet_id) == ("s9", 0)
    created = json.loads(google.requests[1].content)
    assert created["parents"] == ["fold"] and created["appProperties"] == {"zela_item": "people"}
    requests = json.loads(google.requests[-1].content)["requests"]
    kinds = [next(iter(r)) for r in requests]
    assert kinds == [
        "updateSheetProperties",
        "updateCells",
        "addProtectedRange",
        "setDataValidation",
    ]
    assert requests[2]["addProtectedRange"]["protectedRange"]["warningOnly"] is True
    rule = requests[3]["setDataValidation"]["rule"]
    assert rule["strict"] is False and rule["condition"]["type"] == "ONE_OF_LIST"


def test_column_letters():
    assert [column_letter(i) for i in (0, 25, 26, 51, 701, 702)] == [
        "A",
        "Z",
        "AA",
        "AZ",
        "ZZ",
        "AAA",
    ]


def test_upload_is_multipart_related_and_download_returns_bytes():
    def upload(request: httpx.Request) -> httpx.Response:
        content_type = request.headers["content-type"]
        assert content_type.startswith("multipart/related; boundary=")
        body = request.content
        assert b'"parents": ["folder1"]' in body and b'"zela_item": "document:m1"' in body
        assert b"Content-Type: application/pdf\r\n\r\n%PDF-1.4" in body
        return httpx.Response(200, json={"id": "f9"})

    google = Google(
        [
            TOKEN,
            ("POST", "/upload/drive/v3/files?uploadType=multipart", upload),
            ("GET", "/drive/v3/files/f9?alt=media", httpx.Response(200, content=b"%PDF-1.4 x")),
        ]
    )
    ws = google.client().workspace("rt")
    file_id = ws.upload_file(
        "Regimento.pdf",
        mime_type="application/pdf",
        data=b"%PDF-1.4 x",
        folder_id="folder1",
        app_properties={"zela_item": "document:m1"},
    )
    assert file_id == "f9" and ws.download_file("f9") == b"%PDF-1.4 x"
    assert all(r.headers["authorization"] == "Bearer at" for r in google.requests[1:])
