"""Table: reading and writing a register that people also edit by hand."""

import pytest

from app.integrations.google.base import SCOPES
from app.integrations.google.fake import FakeGoogle
from app.registers.specs import PEOPLE
from app.registers.table import RowNotFound, SheetLayoutError, Table, normalize_header


@pytest.fixture
def sheet():
    google = FakeGoogle()
    grant = google.exchange_code(google.issue_code("sindico@example.com", SCOPES))
    ws = google.workspace(grant.refresh_token)
    ref = ws.create_spreadsheet(
        "Pessoas",
        folder_id="folder",
        tab_title="Pessoas",
        headers=PEOPLE.headers,
        choices=PEOPLE.choices,
        app_properties={},
    )
    tab = google.tab(ref.spreadsheet_id)
    return ws, ref, tab


def _table(sheet) -> Table:
    ws, ref, _ = sheet
    return Table(ws, ref.spreadsheet_id, ref.sheet_id, PEOPLE).load()


def test_append_is_idempotent_by_zela_id(sheet):
    table = _table(sheet)
    first = table.append("p1", {"name": "Ana", "unit": "101"})
    again = table.append("p1", {"name": "Outro nome"})
    assert again is first and first.number == 2
    assert len(sheet[2].rows) == 2
    # Also across loads: the row is found in the sheet, not only in memory.
    assert _table(sheet).append("p1", {"name": "x"}).values["name"] == "Ana"
    assert len(sheet[2].rows) == 2


def test_reordered_and_extra_columns_are_respected(sheet):
    tab = sheet[2]
    _table(sheet).append("p1", {"name": "Ana", "whatsapp": "+5511987654321"})
    # The manager moves "Nome" to the end, adds a column of their own and fills it in.
    width = len(tab.rows[0])
    name_at = tab.rows[0].index("Nome")
    for i, row in enumerate(tab.rows):
        row.extend([""] * (width - len(row)))
        row.append(row.pop(name_at))
        row.append("Garagem" if i == 0 else "vaga 12")

    table = _table(sheet)
    assert table.find("p1").values["name"] == "Ana"
    table.update("p1", {"name": "Ana Souza"})
    row = tab.rows[1]
    assert row[tab.rows[0].index("Nome")] == "Ana Souza"
    assert row[tab.rows[0].index("Garagem")] == "vaga 12"

    added = table.append("p2", {"name": "Bruno"})
    assert tab.rows[added.number - 1][tab.rows[0].index("Nome")] == "Bruno"


def test_headers_match_ignoring_accents_case_and_spacing(sheet):
    tab = sheet[2]
    tab.rows[0][tab.rows[0].index("Situação")] = "  situacao "
    tab.rows.append(["p1", "Ana", "", "", "", "", "Ativo"])
    assert _table(sheet).find("p1").values["status"] == "Ativo"
    assert normalize_header("Situação") == normalize_header("SITUACAO")


def test_blank_rows_and_hand_added_rows_are_read(sheet):
    tab = sheet[2]
    tab.rows += [["", "", ""], ["", "Carla"], []]
    rows = _table(sheet).rows
    assert [(r.number, r.zela_id, r.values["name"]) for r in rows] == [(3, "", "Carla")]


def test_update_writes_only_the_changed_cells(sheet):
    table = _table(sheet)
    table.append("p1", {"name": "Ana", "notes": "síndica anterior"})
    sheet[2].rows[1][PEOPLE.headers.index("Observações")] = "editado à mão"
    table.update("p1", {"status": "Inativo"})
    row = sheet[2].rows[1]
    assert row[PEOPLE.headers.index("Situação")] == "Inativo"
    assert row[PEOPLE.headers.index("Observações")] == "editado à mão"


def test_values_are_cleaned_and_keys_checked(sheet):
    table = _table(sheet)
    row = table.append("p1", {"name": "  Ana\x00\x07 ", "notes": "x" * 6000})
    assert row.values["name"] == "Ana" and len(row.values["notes"]) == 5000
    with pytest.raises(KeyError):
        table.append("p2", {"apartment": "101"})
    with pytest.raises(RowNotFound):
        table.update("nope", {"name": "x"})
    # The ID can't be overwritten through update.
    table.update("p1", {"zela_id": "other", "name": "Ana B"})
    assert table.find("p1").values["name"] == "Ana B"


def test_a_cleared_sheet_gets_its_header_back(sheet):
    sheet[2].rows.clear()
    table = _table(sheet)
    assert sheet[2].rows[0] == PEOPLE.headers
    assert table.rows == []


def test_a_header_without_the_id_column_is_a_layout_error(sheet):
    sheet[2].rows[0][0] = "Código interno"
    with pytest.raises(SheetLayoutError, match="ID Zela"):
        _table(sheet)
