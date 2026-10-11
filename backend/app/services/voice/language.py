"""Language handling for Telugu / English / code-mixed (Tenglish) speech.

Whisper reports one language per clip, which is wrong for code-mixed
speech, so the final label also looks at the transcript's script:
Telugu-script words + Latin words -> "mixed". Romanised Telugu ("total
budget entha?") is caught with a small list of very common Telugu words.
"""

import re
from typing import Literal

LanguageMode = Literal["auto", "te", "en"]
DetectedLanguage = Literal["te", "en", "mixed"]

LANGUAGE_MODES: tuple[str, ...] = ("auto", "te", "en")

_TELUGU_WORD = re.compile(r"[ఀ-౿]+")
_LATIN_WORD = re.compile(r"[A-Za-z]+")

# Frequent function/question words in romanised Telugu. Only words that are
# NOT also common English words, so plain English is never relabelled.
_ROMANISED_TELUGU = {
    "enti", "entha", "enta", "ela", "elaa", "evaru", "ekkada", "eppudu", "enduku", "enni",
    "cheppu", "cheppandi", "chupinchu", "chupinchandi", "chudu", "kavali", "ledu", "leda",
    "undi", "unnayi", "unnai", "unnadi", "naaku", "naku", "meeku", "miku", "nenu", "meeru",
    "mee", "naa", "ee", "aa", "inka", "kuda", "kooda", "matrame", "anni", "andi", "emiti",
    "emi", "lo", "ki", "nunchi", "varaku", "ayindi", "avvaledu", "cheyyali", "ivvandi",
}

# Whisper's verbose_json reports the language as an English name; Gemini or
# other callers may use ISO codes.
_LANGUAGE_NAMES = {"telugu": "te", "te": "te", "english": "en", "en": "en"}


def normalize_stt_language(raw: str | None) -> str | None:
    """Map an STT-reported language ("Telugu", "english", "te") to an ISO code, or None if unknown."""
    if not raw:
        return None
    return _LANGUAGE_NAMES.get(raw.strip().lower())


def classify_transcript(text: str, stt_language: str | None = None) -> DetectedLanguage:
    """Label a transcript as te / en / mixed from its script mix, using the
    STT's own guess only as a tie-breaker."""
    telugu_words = len(_TELUGU_WORD.findall(text))
    latin_words = [w.lower() for w in _LATIN_WORD.findall(text)]
    romanised = sum(1 for w in latin_words if w in _ROMANISED_TELUGU)
    english_words = len(latin_words) - romanised

    if telugu_words and english_words:
        return "mixed"
    if telugu_words:
        return "te"
    if romanised and english_words:
        return "mixed"
    if romanised:
        return "te"
    if english_words:
        return "en"
    return "te" if normalize_stt_language(stt_language) == "te" else "en"


_REPLY_INSTRUCTIONS: dict[str, str] = {
    "te": (
        "The user is speaking Telugu. Reply in natural spoken Telugu written in Telugu script "
        "(తెలుగు లిపి). Keep worksheet and field names exactly as they appear in the data, and "
        "write numbers as digits."
    ),
    "en": "The user is speaking English. Reply in clear, simple English.",
    "mixed": (
        "The user is speaking a natural mix of Telugu and English (Tenglish). Reply in the same "
        "code-mixed style an Indian speaker would use: Telugu words in Telugu script, and common "
        "English business/technical words (budget, total, pending, tasks, worksheet and field "
        "names) left in English. Write numbers as digits."
    ),
}

_VOICE_STYLE = (
    "Your reply will be read aloud by a text-to-speech voice. Answer in one to three short "
    "spoken sentences. Do not use markdown, tables, bullet lists, emoji, URLs or record IDs. "
    "For lists, mention at most three items and say how many there are in total. Briefly name "
    "the worksheet a number came from. If the question is unclear, ask one short clarifying question."
)


def reply_instruction(language: DetectedLanguage) -> str:
    """System-prompt addendum making the model answer in the user's language, speakably."""
    return f"Voice mode:\n{_REPLY_INSTRUCTIONS[language]}\n{_VOICE_STYLE}"


def browser_voice_lang(language: DetectedLanguage) -> str:
    """BCP-47 tag the frontend should pick a speechSynthesis voice for.
    Mixed replies are mostly Telugu script, so they need a Telugu voice."""
    return "en-IN" if language == "en" else "te-IN"
