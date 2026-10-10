from dataclasses import dataclass, field


@dataclass
class ParsedColumn:
    name: str
    position: int
    inferred_type: str
    confidence: float


@dataclass
class ParsedSheet:
    name: str
    sheet_index: int
    row_count: int
    columns: list[ParsedColumn] = field(default_factory=list)
    sample_rows: list[dict] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    warning: str | None = None


@dataclass
class ParseResult:
    sheets: list[ParsedSheet] = field(default_factory=list)


class ParsingError(Exception):
    """Base class for parsing failures. ``code`` maps to a stable API error code."""

    code = "PARSE_ERROR"


class UnsupportedFileType(ParsingError):
    code = "UNSUPPORTED_FILE_TYPE"


class FileTooLarge(ParsingError):
    code = "FILE_TOO_LARGE"


class CorruptFile(ParsingError):
    code = "CORRUPT_FILE"


class EmptyWorkbook(ParsingError):
    code = "EMPTY_WORKBOOK"
