"""Deterministic, rule-based portal title generation from an uploaded
filename -- no AI. The original filename is never touched; this only
derives a display label.

Pipeline: strip the extension -> strip a duplicate-file suffix like "(1)"
or "copy" -> try to recognize a business domain from keywords in the
cleaned name -> if (and only if) exactly one domain wins confidently, use
its title; otherwise fall back to a cleaned, title-cased version of the
filename rather than guessing a domain.
"""

import re

from app.services.analysis.text import humanize

_FILLER_WORDS = {
    "sample",
    "data",
    "dataset",
    "export",
    "exported",
    "final",
    "draft",
    "copy",
    "backup",
    "test",
    "demo",
    "template",
    "untitled",
    "file",
    "sheet",
    "workbook",
    "new",
    "old",
    "latest",
    "temp",
    "v1",
    "v2",
    "v3",
    "version",
}

# Each entry is (keyword phrases, resulting title). A domain is only used
# when it has strictly more keyword matches than every other domain --
# ties or zero matches fall back to the cleaned filename instead of
# guessing, per the "don't invent a domain" rule.
DOMAIN_RULES: list[tuple[tuple[str, ...], str]] = [
    (("real estate", "construction", "contractor", "renovation"), "Real Estate Construction Management Portal"),
    (("inventory", "warehouse", "stock"), "Inventory Management Portal"),
    (("sales", "crm", "retail order"), "Sales Management Portal"),
    (("human resources", "payroll", "recruitment", " hr "), "HR Management Portal"),
    (("finance", "accounting", "invoicing", "expense tracking"), "Finance Management Portal"),
    (("healthcare", "patient", "clinic", "hospital"), "Healthcare Management Portal"),
    (("education", "student", "curriculum", "enrollment"), "Education Management Portal"),
    (("logistics", "shipping", "fleet", "delivery"), "Logistics Management Portal"),
]

_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_NUMERIC_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")
_COPY_SUFFIX_RE = re.compile(r"[\s_\-]*copy(?:[\s_\-]*\d+)?\s*$", re.IGNORECASE)
_SEPARATORS_RE = re.compile(r"[_\-]+")


def _strip_extension(name: str) -> str:
    return _EXTENSION_RE.sub("", name)


def _strip_duplicate_suffix(name: str) -> str:
    name = _NUMERIC_SUFFIX_RE.sub("", name)
    name = _COPY_SUFFIX_RE.sub("", name)
    return name


def _strip_filler_words(words: list[str]) -> list[str]:
    filtered = [w for w in words if w.lower() not in _FILLER_WORDS]
    # Don't strip a name down to nothing -- an all-filler name (e.g. just
    # "sample_data") still needs something to show.
    return filtered if filtered else words


def _detect_domain(normalized: str) -> str | None:
    padded = f" {normalized} "  # so a bare "hr" keyword can require word boundaries
    best_title: str | None = None
    best_count = 0
    second_count = 0
    for keywords, title in DOMAIN_RULES:
        count = sum(1 for kw in keywords if kw in padded)
        if count > best_count:
            second_count = best_count
            best_count = count
            best_title = title
        elif count > second_count:
            second_count = count
    if best_count == 0 or best_count == second_count:
        return None
    return best_title


def generate_portal_title(original_filename: str) -> str:
    base = _strip_extension(original_filename.strip())
    base = _strip_duplicate_suffix(base)

    normalized_for_domain = _SEPARATORS_RE.sub(" ", base).lower()
    domain_title = _detect_domain(normalized_for_domain)
    if domain_title:
        return domain_title

    spaced = _SEPARATORS_RE.sub(" ", base)
    words = [w for w in spaced.split() if w]
    words = _strip_filler_words(words)
    cleaned = " ".join(words).strip()
    if not cleaned:
        return "Business Portal"
    return humanize(cleaned)
