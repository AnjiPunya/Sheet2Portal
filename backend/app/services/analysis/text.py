import re


def humanize(name: str) -> str:
    """Turn a raw worksheet/column name into a display label.

    "purchase_requests" -> "Purchase Requests", "projectName" -> "Project Name"
    """
    spaced = re.sub(r"[_\-]+", " ", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    return " ".join(word.capitalize() for word in spaced.split())


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
