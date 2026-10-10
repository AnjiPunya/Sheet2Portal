from app.services.parsing.inference import dedupe_header, infer_column_type


def test_dedupe_header_handles_duplicates_and_blanks():
    assert dedupe_header(["Name", "Name", None, "Name"]) == [
        "Name",
        "Name (2)",
        "Column 3",
        "Name (3)",
    ]


def test_infer_column_type_all_ints():
    assert infer_column_type([1, 2, 3]) == ("int", 1.0)


def test_infer_column_type_mixed_int_float_reports_float():
    inferred_type, confidence = infer_column_type([1, 2.5, 3])
    assert inferred_type == "float"
    assert confidence == 1.0


def test_infer_column_type_numeric_strings():
    assert infer_column_type(["1", "2", "3"]) == ("int", 1.0)


def test_infer_column_type_dates():
    assert infer_column_type(["2024-01-01", "2024-02-01"]) == ("date", 1.0)


def test_infer_column_type_mostly_string_with_outlier():
    inferred_type, confidence = infer_column_type(["abc", "def", "123"])
    assert inferred_type == "string"
    assert confidence == round(2 / 3, 2)


def test_infer_column_type_all_null_is_unknown():
    assert infer_column_type([None, None, ""]) == ("unknown", 0.0)
