"""Lightweight per-column data-type inference from a sample of cell values.

This is a heuristic, not a guarantee: it exists to give Stage 2's AI schema
mapping something to start from (with a confidence score it can override),
not to be the final word on a column's type.
"""

from datetime import date, datetime

_BOOL_LITERALS = {"true", "false", "yes", "no"}


def _is_bool(value: str) -> bool:
    return value.strip().lower() in _BOOL_LITERALS


def _is_int(value: str) -> bool:
    try:
        int(value.strip())
        return True
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    try:
        float(value.strip())
        return True
    except ValueError:
        return False


def _is_date_string(value: str) -> bool:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            datetime.strptime(value.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def classify_value(value: object) -> str:
    """Classify a single already-typed (Excel) or raw string (CSV) value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (datetime, date)):
        return "date"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    text = str(value)
    if text.strip() == "":
        return "null"
    if _is_bool(text):
        return "bool"
    if _is_int(text):
        return "int"
    if _is_float(text):
        return "float"
    if _is_date_string(text):
        return "date"
    return "string"


def dedupe_header(raw_names: list[object]) -> list[str]:
    """Turn a raw header row into unique, display-ready column names."""
    seen: dict[str, int] = {}
    names: list[str] = []
    for idx, value in enumerate(raw_names):
        name = str(value).strip() if value is not None and str(value).strip() != "" else f"Column {idx + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        names.append(name)
    return names


def infer_column_type(values: list[object]) -> tuple[str, float]:
    """Return (inferred_type, confidence) for a column given sample values.

    Confidence is the fraction of non-null samples that agree with the
    winning type. An all-null column is reported as ``unknown`` with 0
    confidence rather than guessing.
    """
    classifications = [classify_value(v) for v in values]
    non_null = [c for c in classifications if c != "null"]
    if not non_null:
        return "unknown", 0.0

    counts: dict[str, int] = {}
    for c in non_null:
        counts[c] = counts.get(c, 0) + 1

    # int values also satisfy "float", so numeric columns that mix the two
    # should be reported as float rather than penalized for disagreeing.
    if counts.get("int", 0) and counts.get("float", 0):
        counts["float"] = counts.get("float", 0) + counts.pop("int")

    winner, matches = max(counts.items(), key=lambda kv: kv[1])
    confidence = matches / len(non_null)
    return winner, round(confidence, 2)
