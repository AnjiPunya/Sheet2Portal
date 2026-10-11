"""Language handling for Telugu / English / code-mixed (Tenglish) speech.

Whisper reports one language per clip, which is wrong for code-mixed
speech, so the final label also looks at the transcript's script:
Telugu-script words + Latin words -> "mixed". Romanised Telugu ("total
budget entha?") is caught with a small list of very common Telugu words.
"""

import re
import unicodedata
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


# Indic scripts share the ISCII-derived layout: each Unicode block is 0x80
# wide and the same offset within a block is (almost always) the same
# letter. Whisper sometimes emits stray Devanagari/Bengali/etc. letters
# inside Telugu words ("ప्रोजেक्स"); shifting them into the Telugu block
# recovers the intended Telugu letters.
_TELUGU_BASE = 0x0C00
_OTHER_INDIC_BASES = (0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80, 0x0C80, 0x0D00)


def _telugu_codepoint_assigned(cp: int) -> bool:
    try:
        unicodedata.name(chr(cp))
        return True
    except ValueError:
        return False


def fold_indic_into_telugu(text: str) -> str:
    """Map stray letters from other Indic scripts into Telugu, but only when
    the text is already mostly Telugu (so genuine Hindi etc. is untouched)."""
    telugu = sum(1 for ch in text if 0x0C00 <= ord(ch) <= 0x0C7F)
    other = sum(1 for ch in text if any(b <= ord(ch) < b + 0x80 for b in _OTHER_INDIC_BASES))
    if not other or telugu < other:
        return text
    out = []
    for ch in text:
        cp = ord(ch)
        base = next((b for b in _OTHER_INDIC_BASES if b <= cp < b + 0x80), None)
        if base is not None:
            target = _TELUGU_BASE + (cp - base)
            # Danda/double danda (U+0964/5) are shared punctuation: keep them.
            if cp not in (0x0964, 0x0965) and _telugu_codepoint_assigned(target):
                ch = chr(target)
        out.append(ch)
    return "".join(out)


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


_REMINDERS: dict[str, str] = {
    "te": "(Voice reply: answer in Telugu, in Telugu script, in 1-3 short sentences, no markdown.)",
    "en": "(Voice reply: answer in English, in 1-3 short sentences, no markdown.)",
    "mixed": (
        "(Voice reply: answer in the same Telugu-English mix -- Telugu words in Telugu script, "
        "English terms in English -- in 1-3 short sentences, no markdown.)"
    ),
}


def reply_reminder(language: DetectedLanguage) -> str:
    """Short per-turn nudge. Models follow the language of the latest user
    turn more reliably than a system-prompt rule alone (live testing: a mixed
    follow-up got an English reply without it)."""
    return _REMINDERS[language]


def browser_voice_lang(language: DetectedLanguage) -> str:
    """BCP-47 tag the frontend should pick a speechSynthesis voice for.
    Mixed replies are mostly Telugu script, so they need a Telugu voice."""
    return "en-IN" if language == "en" else "te-IN"
