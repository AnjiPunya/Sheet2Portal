import os

from app.services.parsing.csv_parser import parse_csv
from app.services.parsing.excel_parser import parse_excel
from app.services.parsing.types import ParseResult, UnsupportedFileType

_PARSERS = {
    ".xlsx": parse_excel,
    ".csv": parse_csv,
}


def parse_workbook(path: str, extension: str, max_rows: int, sample_row_count: int) -> ParseResult:
    parser = _PARSERS.get(extension.lower())
    if parser is None:
        raise UnsupportedFileType(f"Unsupported file extension: {extension}")
    return parser(path, max_rows, sample_row_count)


def extension_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()
