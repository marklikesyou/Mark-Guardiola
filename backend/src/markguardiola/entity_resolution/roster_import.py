from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class ImportedRosterRow:
    name: str
    role: str | None = None
    team: str | None = None
    purchase_price: Decimal | None = None


def parse_roster_text(
    content: bytes, *, max_bytes: int = 2 * 1024 * 1024
) -> list[ImportedRosterRow]:
    text = _validated_text(content, max_bytes=max_bytes)
    rows: list[ImportedRosterRow] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cells = [cell.strip() for cell in _split_line(line)]
        rows.append(
            ImportedRosterRow(
                name=cells[0],
                role=cells[1] or None if len(cells) > 1 else None,
                team=cells[2] or None if len(cells) > 2 else None,
                purchase_price=_decimal(cells[3]) if len(cells) > 3 and cells[3] else None,
            )
        )
    return _validate_rows(rows)


def parse_roster_csv(
    content: bytes, *, max_bytes: int = 2 * 1024 * 1024
) -> list[ImportedRosterRow]:
    text = _validated_text(content, max_bytes=max_bytes)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError()
    normalized_headers = {header.strip().casefold(): header for header in reader.fieldnames}
    name_header = normalized_headers.get("name") or normalized_headers.get("player")
    if name_header is None:
        raise ValueError()
    allowed = {"name", "player", "role", "team", "purchase_price", "price"}
    unknown = set(normalized_headers).difference(allowed)
    if unknown:
        raise ValueError()
    rows: list[ImportedRosterRow] = []
    for row in reader:
        name = (row.get(name_header) or "").strip()
        rows.append(
            ImportedRosterRow(
                name=name,
                role=_optional(row, normalized_headers.get("role")),
                team=_optional(row, normalized_headers.get("team")),
                purchase_price=_decimal_optional(
                    _optional(
                        row,
                        normalized_headers.get("purchase_price") or normalized_headers.get("price"),
                    )
                ),
            )
        )
    return _validate_rows(rows)


def _validated_text(content: bytes, *, max_bytes: int) -> str:
    if len(content) > max_bytes:
        raise ValueError()
    if b"\x00" in content:
        raise ValueError()
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError() from None


def _split_line(line: str) -> list[str]:
    for delimiter in ("\t", ";", ","):
        if delimiter in line:
            return next(csv.reader([line], delimiter=delimiter))
    return [line]


def _validate_rows(rows: list[ImportedRosterRow]) -> list[ImportedRosterRow]:
    if not rows:
        raise ValueError()
    if len(rows) > 500:
        raise ValueError()
    if any(not row.name or len(row.name) > 200 for row in rows):
        raise ValueError()
    return rows


def _optional(row: dict[str, str | None], key: str | None) -> str | None:
    value = row.get(key) if key is not None else None
    stripped = value.strip() if value else None
    return stripped or None


def _decimal_optional(value: str | None) -> Decimal | None:
    return _decimal(value) if value else None


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise ValueError() from None
    if parsed < 0:
        raise ValueError()
    return parsed
