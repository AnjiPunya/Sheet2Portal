import csv

from app.services.parsing.inference import dedupe_header, infer_column_type
from app.services.parsing.types import CorruptFile, EmptyWorkbook, ParsedColumn, ParsedSheet, ParseResult

_INFERENCE_SAMPLE_SIZE = 200
_ENCODINGS = ("utf-8-sig", "latin-1")


def _read_rows(path: str) -> tuple[list[list[str]], str]:
    last_error: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            with open(path, newline="", encoding=encoding) as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.reader(f, dialect)
                return list(reader), encoding
        except (UnicodeDecodeError, OSError) as exc:
            last_error = exc
            continue
    raise CorruptFile(str(last_error) if last_error else "Unable to decode CSV file")


def parse_csv(path: str, max_rows: int, sample_row_count: int) -> ParseResult:
    rows, _ = _read_rows(path)
    rows = [r for r in rows if any(cell.strip() for cell in r)]

    if not rows:
        raise EmptyWorkbook("CSV file has no data")

    column_names = dedupe_header(rows[0])
    data_rows = rows[1:]
    row_count = len(data_rows)
    truncated = row_count > max_rows
    counted_rows = data_rows[:max_rows]

    rows: list[dict] = []
    column_values: list[list[object]] = [[] for _ in column_names]
    for i, row in enumerate(counted_rows):
        padded = list(row) + [None] * (len(column_names) - len(row))
        rows.append(dict(zip(column_names, padded)))
        if i < _INFERENCE_SAMPLE_SIZE:
            for col_idx in range(len(column_names)):
                column_values[col_idx].append(padded[col_idx] if col_idx < len(padded) else None)

    columns = []
    for position, name in enumerate(column_names):
        inferred_type, confidence = infer_column_type(column_values[position])
        columns.append(
            ParsedColumn(name=name, position=position, inferred_type=inferred_type, confidence=confidence)
        )

    warning = f"Row count exceeds {max_rows}; data beyond the limit was not processed" if truncated else None

    sheet = ParsedSheet(
        name="Sheet1",
        sheet_index=0,
        row_count=min(row_count, max_rows),
        columns=columns,
        sample_rows=rows[:sample_row_count],
        rows=rows,
        warning=warning,
    )
    return ParseResult(sheets=[sheet])
