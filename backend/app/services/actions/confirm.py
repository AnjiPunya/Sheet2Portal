"""Deterministic yes / no detection for a pending draft (no AI involved).

An utterance only confirms (or cancels) when *every* word in it is a
confirmation (or cancellation) word or a filler. Anything else -- "yes but
make it 6 crore", "no, the other project" -- is a correction and goes to the
model as a normal turn, which can revise the draft. Telugu script, romanised
Telugu and English are all covered, since voice transcripts mix them.
"""

import re
from typing import Literal

Decision = Literal["confirm", "cancel", "other"]

_CONFIRM = {
    # English
    "yes", "yeah", "yep", "yup", "ya", "confirm", "confirmed", "ok", "okay", "sure", "correct", "right",
    "proceed", "go", "ahead", "do", "done", "fine", "absolutely", "definitely",
    # Telugu (script)
    "అవును", "అవునండి", "అవ్వును", "సరే", "సరేనండి", "సరి", "ఓకే", "ఒకే", "చేయి", "చేయండి", "చెయ్యి", "చెయ్యండి",
    "కన్ఫర్మ్", "ముందుకు", "వెళ్ళు", "వెళ్ళండి", "కానివ్వు", "కానివ్వండి", "ఖచ్చితంగా",
    # Telugu (romanised)
    "avunu", "avnu", "sare", "sari", "cheyyi", "cheyandi", "cheyyandi", "kanivvu", "kanivvandi",
}
_CANCEL = {
    # English
    "no", "nope", "nah", "cancel", "cancelled", "stop", "dont", "don't", "never", "mind", "abort", "discard", "forget",
    # Telugu (script)
    "వద్దు", "వద్దండి", "క్యాన్సిల్", "కాన్సిల్", "ఆపు", "ఆపండి", "రద్దు", "లేదు", "మర్చిపో",
    # Telugu (romanised)
    "vaddu", "vaddandi", "apu", "aapu", "apandi", "radhu", "raddu", "ledu",
}
# Words that may surround a yes/no without changing it.
_FILLER = {
    "please", "it", "that", "this", "the", "is", "thanks", "thank", "you", "ji", "sir", "madam", "just", "now", "and",
    "cheyi", "చేసేయ్", "చేసేయండి", "అండి", "andi", "గారు", "garu", "ఇది", "అది", "idi", "adi", "plz", "pls",
}
_MAX_WORDS = 6
_WORD = re.compile(r"[\wఀ-౿']+")


def classify(utterance: str | None) -> Decision:
    if not utterance:
        return "other"
    words = [w.lower() for w in _WORD.findall(utterance)]
    words = [w for w in words if w not in _FILLER]
    if not words or len(words) > _MAX_WORDS:
        return "other"
    if all(w in _CONFIRM for w in words):
        return "confirm"
    if all(w in _CANCEL for w in words):
        return "cancel"
    return "other"
