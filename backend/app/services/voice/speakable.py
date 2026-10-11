"""Turn a chat reply (possibly markdown) into text a TTS voice can read naturally."""

import re

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s*>\s?", re.MULTILINE)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.MULTILINE)
_HR = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$", re.MULTILINE)
# Record ids (uuids / long hex) are meaningless when read aloud.
_UUID = re.compile(r"#?\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def _table_row_to_sentence(line: str) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return ", ".join(c for c in cells if c) + "."


def to_speakable(text: str, max_chars: int = 600) -> str:
    """Strip markdown/tables/ids/emoji and trim to ``max_chars`` at a sentence boundary."""
    if not text:
        return ""
    out = _CODE_FENCE.sub(" ", text)
    out = _TABLE_RULE.sub("", out)
    out = "\n".join(_table_row_to_sentence(line) if line.count("|") >= 2 else line for line in out.splitlines())
    out = _IMAGE.sub(r"\1", out)
    out = _LINK.sub(r"\1", out)
    out = _URL.sub("", out)
    out = _INLINE_CODE.sub(r"\1", out)
    out = _HR.sub("", out)
    out = _HEADING.sub("", out)
    out = _BLOCKQUOTE.sub("", out)
    out = _LIST_MARKER.sub("", out)
    for _ in range(2):  # nested emphasis, e.g. **_x_**
        out = _EMPHASIS.sub(r"\2", out)
    out = _UUID.sub("", out)
    out = _EMOJI.sub("", out)

    # Each remaining line becomes a sentence, so list items don't run together.
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    sentences = [line if line[-1] in ".!?:;,।" else f"{line}." for line in lines]
    out = re.sub(r"\s+", " ", " ".join(sentences)).strip()
    out = re.sub(r"\s+([.,!?;:])", r"\1", out)
    out = re.sub(r"([.!?])\.+", r"\1", out)

    if len(out) <= max_chars:
        return out
    trimmed = ""
    for sentence in _SENTENCE_END.split(out):
        candidate = f"{trimmed} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        trimmed = candidate
    return trimmed or out[:max_chars].rsplit(" ", 1)[0] + "…"
