"""Spoken Indian-English / Telugu amounts -> numbers ("5 crore" -> 50000000).

The model is asked to send plain numbers, but speech often arrives as
"5 crore", "2.5 lakh", "3 కోట్లు" or "₹40,000"; converting deterministically
here means the draft shows the exact value that will be saved.
"""

import re

_UNITS = {
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000, "కోటి": 10_000_000, "కోట్లు": 10_000_000, "koti": 10_000_000, "kotlu": 10_000_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "l": 100_000, "లక్ష": 100_000, "లక్షలు": 100_000, "laksha": 100_000, "lakshalu": 100_000,
    "thousand": 1_000, "k": 1_000, "వేలు": 1_000, "వెయ్యి": 1_000, "velu": 1_000,
    "million": 1_000_000, "mn": 1_000_000, "billion": 1_000_000_000,
}
_AMOUNT = re.compile(r"^\s*(?:₹|rs\.?|inr)?\s*(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>[^\d\s.,]+)?\s*(?:rupees|రూపాయలు)?\s*$", re.I)


def parse_amount(value: object) -> object:
    """Return a number for an amount-like string; anything else unchanged."""
    if not isinstance(value, str):
        return value
    match = _AMOUNT.match(value.replace(" ", " "))
    if not match:
        return value
    number = float(match.group("number").replace(",", ""))
    unit = (match.group("unit") or "").lower().rstrip(".")
    if unit and unit not in _UNITS:
        return value
    result = number * _UNITS.get(unit, 1)
    return int(result) if float(result).is_integer() else result
