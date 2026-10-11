"""What a column *means*, from its name and values -- shared by KPIs,
charts, forms and validation so they all agree. Deterministic, no AI.

Every check is generic (works for any workbook): percentages, per-unit
prices, ratings, phone numbers, emails, clock times, optional free-text
notes, and documentation/reference worksheets.
"""

import re

from app.services.analysis.text import normalize_key


def _words(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return re.findall(r"[a-z0-9%]+", spaced.lower())


def is_percent(name: str) -> bool:
    words = _words(name)
    return "%" in name or "percent" in words or "percentage" in words or "pct" in words


def is_per_unit(name: str) -> bool:
    """A rate or unit price (Unit_Cost, Price_Per_Kg, Daily_Rate): summing
    these across rows means nothing."""
    words = _words(name)
    if "per" in words or "rate" in words or "price" in words:
        return True
    return "unit" in words and any(w in words for w in ("cost", "price", "rate", "value"))


def rating_max(name: str, values: list[float]) -> float | None:
    """Upper bound for a rating/score column (Rating_Out_of_5 -> 5)."""
    match = re.search(r"out\s*of\s*(\d+)", name.replace("_", " "), re.I)
    if match:
        return float(match.group(1))
    words = _words(name)
    if "rating" in words or "stars" in words or "score" in words:
        top = max(values, default=0)
        for bound in (5.0, 10.0, 100.0):
            if top <= bound:
                return bound
    return None


def is_phone(name: str) -> bool:
    key = normalize_key(name)
    return any(h in key for h in ("phone", "mobile", "whatsapp", "telephone", "contactno", "contactnumber", "cellno")) or key in (
        "tel",
        "zip",
        "zipcode",
        "pincode",
        "postcode",
        "postalcode",
    )


def is_email(name: str, values: list[object]) -> bool:
    texts = [str(v) for v in values if v not in (None, "")]
    return "email" in normalize_key(name) or (bool(texts) and all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t) for t in texts))


_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")


def is_time(values: list[object]) -> bool:
    texts = [str(v).strip() for v in values if v not in (None, "")]
    return bool(texts) and all(_TIME.match(t) for t in texts)


def valid_time(text: str) -> bool:
    return bool(_TIME.match(text.strip()))


def allows_negative(name: str) -> bool:
    """Quantities that can legitimately go below zero."""
    words = set(_words(name))
    return bool(words & {"temperature", "temp", "change", "variance", "delta", "difference", "profit", "net", "balance", "loss", "adjustment"})


_OPTIONAL_TEXT = ("note", "remark", "comment", "photo", "attachment", "image", "reference", "dependency", "blocker", "delay", "safety", "withdrawal", "additional", "misc")


def is_optional_text(name: str) -> bool:
    """Free-text extras (notes, remarks, photo references) never block saving,
    even when every existing row happens to have one."""
    key = normalize_key(name)
    return any(h in key for h in _OPTIONAL_TEXT)


_REFERENCE_SHEETS = re.compile(
    r"^(read\s*me|data\s*dictionary|dictionary|glossary|instructions?|about|help|notes|"
    r"(dashboard\s*)?kpis?(\s*definitions?)?|kpi\s*definitions?|roles?\s*(and\s*|&\s*)?permissions?|permissions?)$",
    re.I,
)


def is_reference_sheet(name: str) -> bool:
    """Documentation sheets bundled with a workbook (README, Data Dictionary,
    KPI definitions, Roles & Permissions): shown read-only, never totalled,
    charted or edited."""
    return bool(_REFERENCE_SHEETS.match(re.sub(r"[_\-]+", " ", name).strip()))


# Stock movement words, for the "can't use more than is in stock" rule.
_CONSUMPTION = ("used", "usage", "consum", "issued", "issue", "sold", "sale", "dispatch", "withdraw", "log", "order", "feed", "outbound", "out")
_INBOUND = ("purchase", "request", "receipt", "received", "restock", "inbound", "procure", "delivery", "supply", "supplies", "stocking")
_STOCK = ("stock", "onhand", "available", "inventory", "balance", "instock")


def is_consumption_sheet(name: str) -> bool:
    key = normalize_key(name)
    if any(h in key for h in _INBOUND):
        return False
    return any(h in key for h in _CONSUMPTION)


def is_stock_column(name: str) -> bool:
    key = normalize_key(name)
    return any(h in key for h in _STOCK) and "reorder" not in key and "level" not in key


_DATE_START = ("start", "stocking", "raised", "reported", "request", "issued", "opened", "created", "order", "treatment", "reading", "sample", "planned start")
_DATE_END = ("end", "due", "target", "needed", "harvest", "followup", "resolution", "close", "complete", "delivery", "expiry", "deadline")


def date_role(name: str) -> str | None:
    """'start' or 'end' for date columns whose names say so (used for the
    end-not-before-start rule)."""
    key = normalize_key(name)
    if any(normalize_key(h) in key for h in _DATE_END):
        return "end"
    if any(normalize_key(h) in key for h in _DATE_START):
        return "start"
    return None
