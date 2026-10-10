"""Convert raw cell values (which may be native Python date/datetime/Decimal
objects from openpyxl) into JSON-serializable values before they're stored in
a JSON database column.
"""

from datetime import date, datetime, time
from decimal import Decimal


def json_safe(value: object) -> object:
    if isinstance(value, datetime):
        # Excel date-only cells come back as datetime at midnight; drop the
        # time component so they don't render as "2024-01-10T00:00:00".
        if value.time() == time(0, 0):
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def json_safe_row(row: dict) -> dict:
    return {key: json_safe(value) for key, value in row.items()}
