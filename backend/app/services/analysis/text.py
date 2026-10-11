import re


def humanize(name: str) -> str:
    """Turn a raw worksheet/column name into a display label.

    "purchase_requests" -> "Purchase Requests", "Project_Manager" -> "Project
    Manager", "projectName" -> "Project Name", "PR_ID" -> "PR ID". Acronyms
    are kept unless the whole name is shouted ("PURCHASE_REQUESTS"). Display
    only -- data, filters and relationships keep the original name. Mirrored
    by ``formatLabel`` in the frontend (frontend/src/lib/labels.ts).
    """
    spaced = re.sub(r"[_\-]+", " ", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    all_caps = not any(ch.islower() for ch in name)
    return " ".join(_display_word(word, all_caps) for word in spaced.split())


# Kept upper-case even inside an all-caps name like "PR_ID" or "ITEM_SKU".
_ACRONYMS = frozenset(
    {"ID", "PR", "PO", "SKU", "HR", "GST", "VAT", "UOM", "KPI", "ETA", "URL", "API", "USD", "INR", "EUR", "GBP", "QTY"}
)


def _display_word(word: str, all_caps_name: bool) -> str:
    if word.upper() in _ACRONYMS:
        return word.upper()
    if all_caps_name:
        return word.capitalize()
    if word.isupper():  # an acronym in a mixed-case name, e.g. "Unit CBM"
        return word
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
