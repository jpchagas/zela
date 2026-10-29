"""One register's rows, read from the manager's spreadsheet.

People edit these sheets by hand, so a Table tolerates reordered and extra columns,
blank rows and rows without a Zela ID. Callers hold the condominium's sheet lock
(services.drive.sheet_lock) from load() to their last write.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.integrations.google.base import Cell, Workspace
from app.registers.specs import ID, RegisterSpec

MAX_CELL_CHARS = 5000
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class SheetLayoutError(Exception):
    """The sheet can't be read safely. `message` is pt-BR, for the manager."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RowNotFound(Exception):
    pass


@dataclass
class Row:
    number: int  # as shown in the sheet
    values: dict[str, str]

    @property
    def zela_id(self) -> str:
        return self.values.get(ID.key, "")


def normalize_header(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def clean_value(value: object) -> str:
    text = _CONTROL.sub("", "" if value is None else str(value)).strip()
    return text[:MAX_CELL_CHARS]


class Table:
    def __init__(
        self, workspace: Workspace, spreadsheet_id: str, sheet_id: int, spec: RegisterSpec
    ):
        self._ws = workspace
        self._spreadsheet_id = spreadsheet_id
        self._sheet_id = sheet_id
        self.spec = spec
        self.rows: list[Row] = []
        self._col: dict[str, int] = {}

    def load(self) -> "Table":
        values = self._ws.read_values(self._spreadsheet_id, self._sheet_id)
        header = values[0] if values else []
        positions: dict[str, int] = {}
        for i, text in enumerate(header):
            key = normalize_header(text)
            if key and key not in positions:
                positions[key] = i

        if header and normalize_header(ID.header) not in positions:
            raise SheetLayoutError(
                f'A planilha "{self.spec.title}" está sem a coluna "{ID.header}" na primeira '
                "linha. Restaure o cabeçalho para o Zela voltar a usá-la."
            )

        # New columns (or a fully cleared sheet) get their headers added at the end.
        missing = [c for c in self.spec.columns if normalize_header(c.header) not in positions]
        if missing:
            start = len(header)
            cells = [Cell(1, start + i, c.header) for i, c in enumerate(missing)]
            self._ws.update_cells(self._spreadsheet_id, self._sheet_id, cells)
            for cell, column in zip(cells, missing, strict=True):
                positions[normalize_header(column.header)] = cell.col

        self._col = {c.key: positions[normalize_header(c.header)] for c in self.spec.columns}
        self.rows = []
        for number, raw in enumerate(values[1:], start=2):
            if not any(cell.strip() for cell in raw):
                continue
            self.rows.append(Row(number, {k: _at(raw, i).strip() for k, i in self._col.items()}))
        return self

    def find(self, zela_id: str) -> Row | None:
        if not zela_id:
            return None
        return next((r for r in self.rows if r.zela_id == zela_id), None)

    def append(self, zela_id: str, record: dict[str, object]) -> Row:
        """Adds a row, unless one with this Zela ID exists (then returns it unchanged)."""
        existing = self.find(zela_id)
        if existing is not None:
            return existing
        values = {k: clean_value(v) for k, v in self._checked(record).items()}
        values[ID.key] = zela_id
        line = [""] * (max(self._col.values()) + 1)
        for key, value in values.items():
            line[self._col[key]] = value
        number = self._ws.append_row(self._spreadsheet_id, self._sheet_id, line)
        row = Row(number, {k: values.get(k, "") for k in self._col})
        self.rows.append(row)
        return row

    def update(self, zela_id: str, changes: dict[str, object]) -> Row:
        row = self.find(zela_id)
        if row is None:
            raise RowNotFound(zela_id)
        changes = {k: clean_value(v) for k, v in self._checked(changes).items()}
        changes.pop(ID.key, None)
        cells = [Cell(row.number, self._col[k], v) for k, v in changes.items()]
        self._ws.update_cells(self._spreadsheet_id, self._sheet_id, cells)
        row.values.update(changes)
        return row

    def assign_id(self, row: Row, zela_id: str) -> Row:
        """Gives a hand-added row (no Zela ID yet) an ID, so Zela can update it later."""
        if row.zela_id:
            return row
        self._ws.update_cells(
            self._spreadsheet_id, self._sheet_id, [Cell(row.number, self._col[ID.key], zela_id)]
        )
        row.values[ID.key] = zela_id
        return row

    def _checked(self, record: dict[str, object]) -> dict[str, object]:
        unknown = set(record) - set(self._col)
        if unknown:
            raise KeyError(f"Unknown {self.spec.kind} columns: {sorted(unknown)}")
        return record


def _at(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""
