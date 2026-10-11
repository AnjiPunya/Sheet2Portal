import re


def humanize(name: str) -> str:
    """Turn a raw worksheet/column name into a display label.

    "purchase_requests" -> "Purchase Requests", "Project_Manager" -> "Project
    Manager", "projectName" -> "Project Name", "PR_ID" -> "PR ID". Acronyms
    are kept unless the whole name is shouted ("PURCHASE_REQUESTS"). Display
    only -- data, filters and relationships keep the original name. Mirrored
    by ``formatLabel`` in the frontend (frontend/src/lib/labels.ts).
    """
    if "(" in name:  # already formatted ("Stock (kg)"): format only the part before the suffix
        head, _, tail = name.partition("(")
        return f"{humanize(head)} ({tail}".strip() if head.strip() else name
    spaced = re.sub(r"[_\-]+", " ", name)
    # camelCase -> words, but keep short mixed-case terms like "pH" intact.
    spaced = re.sub(r"(?<=[a-z]{2})(?=[A-Z])|(?<=[0-9])(?=[A-Z])", " ", spaced)
    all_caps = not any(ch.islower() for ch in name)
    words = spaced.split()
    # A trailing unit group becomes a parenthesised suffix:
    # "Stock Kg" -> "Stock (kg)", "Unit Cost INR Per Kg" -> "Unit Cost (INR per kg)".
    start = len(words)
    while start > 1 and _is_unit(words, start - 1, words[start - 1].lower() == "per" and start < len(words)):
        start -= 1
    if words[start:start + 1] and words[start].lower() == "per" and start == len(words) - 1:
        start += 1  # a dangling "per" isn't a unit group
    head = [_display_word(w, all_caps, i) for i, w in enumerate(words[:start])]
    if start < len(words):
        head.append(f"({_unit_group(words[start:], words[start - 1] if start else '')})")
    return " ".join(head)


# Kept upper-case even inside an all-caps name like "PR_ID" or "ITEM_SKU".
_ACRONYMS = frozenset(
    {"ID", "PR", "PO", "SKU", "HR", "GST", "VAT", "UOM", "KPI", "ETA", "URL", "API", "USD", "INR", "EUR", "GBP", "QTY", "PL", "NTU"}
)
# Lower-case connecting words (never the first word).
_SMALL_WORDS = frozenset({"or", "of", "per", "and", "to", "in", "by", "for", "the", "a", "an", "on", "at", "vs", "out"})
# Units, written the conventional way.
_UNITS = {
    "kg": "kg", "g": "g", "mg": "mg", "l": "L", "ml": "mL", "ppt": "ppt", "ppm": "ppm", "ntu": "NTU",
    "acres": "acres", "acre": "acres", "ha": "ha", "hectares": "hectares", "km": "km", "cm": "cm", "mm": "mm",
    "inr": "INR", "usd": "USD", "eur": "EUR", "gbp": "GBP", "percent": "%", "pct": "%", "%": "%",
}


def _is_unit(words: list[str], index: int, connecting_per: bool) -> bool:
    word = words[index].lower()
    if connecting_per:
        return True
    if word == "c":  # Temperature_C -> Temperature (°C); a lone "C" elsewhere isn't a unit
        return index > 0 and words[index - 1].lower() in ("temperature", "temp")
    return word in _UNITS


def _unit_group(units: list[str], previous: str) -> str:
    lowered = [u.lower() for u in units]
    if lowered == ["mg", "l"]:
        return "mg/L"
    if lowered == ["c"] and previous.lower() in ("temperature", "temp"):
        return "°C"
    return " ".join("per" if u == "per" else _UNITS.get(u, u) for u in lowered)


def _display_word(word: str, all_caps_name: bool, index: int = 0) -> str:
    if word.upper() in _ACRONYMS:
        return word.upper()
    if index > 0 and word.lower() in _SMALL_WORDS:
        return word.lower()
    if all_caps_name:
        return word.capitalize()
    if word.isupper():  # an acronym in a mixed-case name, e.g. "Unit CBM"
        return word
    if word[:1].islower() and any(ch.isupper() for ch in word[1:]):
        return word  # mixed-case terms such as "pH" or "eBay" keep their spelling
    return word[:1].upper() + word[1:]


def singularize(label: str) -> str:
    """Best-effort English singularization for a display label (not a column name)."""
    words = label.split(" ")
    if not words:
        return label
    last = words[-1]
    lower = last.lower()
    if lower.endswith("ies") and len(lower) > 3:
        singular = last[:-3] + "y"
    elif lower.endswith(("ses", "xes", "ches", "shes")):
        singular = last[:-2]
    elif lower.endswith("s") and not lower.endswith("ss"):
        singular = last[:-1]
    else:
        singular = last
    return " ".join(words[:-1] + [singular])


def normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())
