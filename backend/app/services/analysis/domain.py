"""Deterministic business-domain detection for a workbook.

Used only to pick the portal's visual theme (dashboard banner image) -- it
never affects parsing, KPIs or any calculation. No AI: each domain has a
keyword list, and the workbook is scored on its worksheet names, column
headers and title. Adding a domain = adding an entry to ``DOMAIN_KEYWORDS``
(plus its images in ``frontend/public/backgrounds`` and an entry in
``frontend/src/lib/backgrounds.ts``).
"""

import re
from collections.abc import Iterable

GENERIC = "generic"

# Single words match whole words (after splitting names on spaces,
# underscores, hyphens and camelCase, with a trailing plural "s" removed);
# multi-word entries match as phrases. Prefer words that are specific to the
# domain -- generic business words (status, amount, date, quantity) appear
# everywhere and are deliberately left out.
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "construction": (
        "construction", "project", "site", "contractor", "subcontractor", "builder", "building",
        "material", "cement", "concrete", "steel", "brick", "crane", "scaffolding", "tender", "boq",
        "milestone", "architect", "drawing", "permit", "snag", "real estate", "property", "plot",
        "flat", "villa", "apartment", "tenant", "lease", "rera", "civil", "structural", "foundation",
    ),
    "aquaculture": (
        "aquaculture", "pond", "fish", "shrimp", "prawn", "hatchery", "fingerling", "fry", "stocking",
        "biomass", "salinity", "dissolved oxygen", "ammonia", "tilapia", "catfish", "salmon", "trout",
        "carp", "fcr", "survival rate", "aerator", "cage", "feed conversion",
    ),
    "retail": (
        "retail", "product", "sku", "inventory", "stock", "order", "customer", "store", "shop", "sale",
        "price", "discount", "supplier", "warehouse", "barcode", "invoice", "reorder", "pos", "cart",
        "shipment", "review", "loyalty", "merchandise", "brand",
    ),
    "agriculture": (
        "agriculture", "crop", "farm", "farmer", "field", "acre", "hectare", "yield", "harvest", "seed",
        "fertilizer", "pesticide", "irrigation", "soil", "livestock", "cattle", "dairy", "sowing",
        "plantation", "tractor", "mandi", "paddy", "wheat", "cotton", "orchard",
    ),
    "healthcare": (
        "healthcare", "patient", "doctor", "clinic", "hospital", "appointment", "diagnosis",
        "prescription", "medication", "medicine", "ward", "bed", "admission", "discharge", "nurse",
        "treatment", "physician", "pharmacy", "lab test", "symptom", "vaccination", "opd", "ipd",
    ),
}

# Worksheet names describe what a workbook is about far more reliably than
# any single column header, so they count more.
_SHEET_WEIGHT = 3
_TITLE_WEIGHT = 2
_COLUMN_WEIGHT = 1
# Below this, the evidence is too thin to theme the portal -- use generic.
_MIN_SCORE = 3


def _words(text: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    words = re.findall(r"[a-z0-9]+", spaced.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]


def _matches(text: str) -> set[str]:
    """Domains whose keywords appear in ``text`` (each domain at most once)."""
    words = _words(text)
    word_set = set(words)
    joined = f" {' '.join(words)} "
    hits = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if (" " in keyword and f" {' '.join(_words(keyword))} " in joined) or keyword in word_set:
                hits.add(domain)
                break
    return hits


def domain_scores(title: str, sheet_names: Iterable[str], column_names: Iterable[str]) -> dict[str, int]:
    scores = dict.fromkeys(DOMAIN_KEYWORDS, 0)
    weighted = [(title, _TITLE_WEIGHT)]
    weighted += [(name, _SHEET_WEIGHT) for name in sheet_names]
    weighted += [(name, _COLUMN_WEIGHT) for name in column_names]
    for text, weight in weighted:
        for domain in _matches(text or ""):
            scores[domain] += weight
    return scores


def detect_domain(title: str, sheet_names: Iterable[str], column_names: Iterable[str]) -> str:
    """The workbook's business domain, or ``"generic"`` when no domain has
    enough evidence or the top two are tied."""
    scores = domain_scores(title, sheet_names, column_names)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (best, best_score), (_, runner_up) = ranked[0], ranked[1]
    if best_score < _MIN_SCORE or best_score == runner_up:
        return GENERIC
    return best
