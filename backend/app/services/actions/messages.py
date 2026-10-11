"""Fixed replies for outcomes the server decides itself (confirm / cancel /
failure). These never come from the model, so a reply can only say
"done" when the backend actually did it."""

import re

_TELUGU = re.compile(r"[ఀ-౿]")

_DONE = {
    "create": ("Done. Created {entity} {label}.", "పూర్తయింది. {entity} {label} సృష్టించాను."),
    "update": ("Done. Updated {entity} {label}.", "పూర్తయింది. {entity} {label} అప్‌డేట్ చేశాను."),
    "delete": ("Done. Deleted {entity} {label}.", "పూర్తయింది. {entity} {label} తొలగించాను."),
    "approve": ("Done. Approved {entity} {label}.", "పూర్తయింది. {entity} {label} ఆమోదించాను."),
    "reject": ("Done. Rejected {entity} {label}.", "పూర్తయింది. {entity} {label} తిరస్కరించాను."),
    "resubmit": ("Done. Resubmitted {entity} {label} for approval.", "పూర్తయింది. {entity} {label} మళ్ళీ ఆమోదానికి పంపాను."),
}
_CANCELLED = ("Cancelled. Nothing was changed.", "రద్దు చేశాను. ఏమీ మార్చలేదు.")
_FAILED = ("That didn't go through: {reason} Nothing was changed.", "అది జరగలేదు: {reason} ఏమీ మార్చలేదు.")


def language_of(text: str | None, hint: str | None = None) -> str:
    if hint in ("te", "mixed"):
        return "te"
    if hint == "en":
        return "en"
    return "te" if text and _TELUGU.search(text) else "en"


def _pick(pair: tuple[str, str], language: str) -> str:
    return pair[1] if language == "te" else pair[0]


def completed(action: str, entity: str, label: str, language: str) -> str:
    return _pick(_DONE[action], language).format(entity=entity.lower(), label=label).replace("  ", " ")


def cancelled(language: str) -> str:
    return _pick(_CANCELLED, language)


def failed(reason: str, language: str) -> str:
    reason = reason.strip()
    if reason and not reason.endswith((".", "!", "?")):
        reason += "."
    return _pick(_FAILED, language).format(reason=reason)
