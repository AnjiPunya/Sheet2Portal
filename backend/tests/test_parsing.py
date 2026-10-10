import pytest

from app.services.parsing.csv_parser import parse_csv
from app.services.parsing.excel_parser import parse_excel
from app.services.parsing.service import extension_of, parse_workbook
from app.services.parsing.types import CorruptFile, EmptyWorkbook, UnsupportedFileType


def test_parse_multi_sheet_xlsx(multi_sheet_xlsx):
    result = parse_excel(multi_sheet_xlsx, max_rows=1000, sample_row_count=20)
    assert [s.name for s in result.sheets] == ["Projects", "Tasks"]

    projects = result.sheets[0]
    assert projects.row_count == 2
    assert [c.name for c in projects.columns] == ["Project", "Budget", "Spent", "Start Date"]
    budget_col = next(c for c in projects.columns if c.name == "Budget")
    assert budget_col.inferred_type == "int"
    date_col = next(c for c in projects.columns if c.name == "Start Date")
    assert date_col.inferred_type == "date"
    assert projects.sample_rows[0]["Project"] == "Website Revamp"

    tasks = result.sheets[1]
    done_col = next(c for c in tasks.columns if c.name == "Done")
    assert done_col.inferred_type == "bool"


def test_parse_empty_sheet_is_flagged_not_fatal(empty_sheet_xlsx):
    result = parse_excel(empty_sheet_xlsx, max_rows=1000, sample_row_count=20)
    assert len(result.sheets) == 1
    assert result.sheets[0].row_count == 0
    assert result.sheets[0].warning == "Sheet is empty"


def test_parse_duplicate_headers_are_deduped(duplicate_header_xlsx):
    result = parse_excel(duplicate_header_xlsx, max_rows=1000, sample_row_count=20)
    names = [c.name for c in result.sheets[0].columns]
    assert names == ["Name", "Name (2)", "Column 3"]


def test_parse_corrupt_xlsx_raises(tmp_path):
    bad_file = tmp_path / "bad.xlsx"
    bad_file.write_bytes(b"not a real xlsx file")
    with pytest.raises(CorruptFile):
        parse_excel(str(bad_file), max_rows=1000, sample_row_count=20)


def test_parse_simple_csv(simple_csv):
    result = parse_csv(simple_csv, max_rows=1000, sample_row_count=20)
    sheet = result.sheets[0]
    assert sheet.row_count == 2
    assert [c.name for c in sheet.columns] == ["Name", "Age", "Active"]
    age_col = next(c for c in sheet.columns if c.name == "Age")
    assert age_col.inferred_type == "int"
    active_col = next(c for c in sheet.columns if c.name == "Active")
    assert active_col.inferred_type == "bool"


def test_parse_empty_csv_raises(empty_csv):
    with pytest.raises(EmptyWorkbook):
        parse_csv(empty_csv, max_rows=1000, sample_row_count=20)


def test_parse_row_limit_truncates_with_warning(tmp_path):
    path = tmp_path / "big.csv"
    lines = ["Name,Value"] + [f"row{i},{i}" for i in range(10)]
    path.write_text("\n".join(lines))
    result = parse_csv(str(path), max_rows=5, sample_row_count=20)
    sheet = result.sheets[0]
    assert sheet.row_count == 5
    assert sheet.warning is not None


def test_extension_of():
    assert extension_of("Report.XLSX") == ".xlsx"
    assert extension_of("data.csv") == ".csv"


def test_parse_workbook_dispatches_by_extension(simple_csv):
    result = parse_workbook(simple_csv, ".csv", max_rows=1000, sample_row_count=20)
    assert result.sheets[0].name == "Sheet1"


def test_parse_workbook_unsupported_extension_raises(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("hello")
    with pytest.raises(UnsupportedFileType):
        parse_workbook(str(path), ".txt", max_rows=1000, sample_row_count=20)
