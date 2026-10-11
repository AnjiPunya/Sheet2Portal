"""Pure-function voice tests: language labelling, speakable text, prompts, silence, audio sniffing."""

import pytest

from app.services.voice.audio import AudioValidationError, pcm_to_wav, sniff_format, validate_audio, wav_duration_seconds
from app.services.voice.language import (
    browser_voice_lang,
    classify_transcript,
    fold_indic_into_telugu,
    normalize_stt_language,
    reply_instruction,
)
from app.services.voice.speakable import to_speakable
from app.services.voice.stt import build_prompt, looks_silent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ఈ నెల మొత్తం బడ్జెట్ ఎంత?", "te"),
        ("What is the total budget?", "en"),
        ("Projects sheet లో total budget ఎంత?", "mixed"),
        ("total budget entha?", "mixed"),  # romanised Telugu + English
        ("naaku enni unnayi cheppu", "te"),  # fully romanised Telugu
    ],
)
def test_classify_transcript(text, expected):
    assert classify_transcript(text) == expected


def test_classify_falls_back_to_stt_language_for_digits_only():
    assert classify_transcript("35000", "Telugu") == "te"
    assert classify_transcript("35000", None) == "en"


def test_normalize_stt_language():
    assert normalize_stt_language("Telugu") == "te"
    assert normalize_stt_language("english") == "en"
    assert normalize_stt_language("Gujarati") is None
    assert normalize_stt_language(None) is None


def test_reply_instruction_matches_language():
    assert "Telugu script" in reply_instruction("te")
    assert "Tenglish" in reply_instruction("mixed")
    assert "English" in reply_instruction("en")
    assert "markdown" in reply_instruction("en")
    assert browser_voice_lang("en") == "en-IN"
    assert browser_voice_lang("mixed") == "te-IN"


def test_speakable_strips_markdown_tables_and_ids():
    md = (
        "## Summary\n\n"
        "The **total budget** is `35000` from [Projects](http://x/y).\n\n"
        "| Project | Budget |\n|---|---|\n| Website Revamp | 10000 |\n| Mobile App | 25000 |\n\n"
        "- First item\n- Second item 🎉\n"
        "See record #0f8fad5b-d9cb-469f-a165-70867728950e for details."
    )
    out = to_speakable(md)
    for junk in ("#", "**", "`", "|", "---", "http", "🎉", "0f8fad5b", "- "):
        assert junk not in out
    assert "The total budget is 35000 from Projects." in out
    assert "Website Revamp, 10000." in out
    assert "First item. Second item." in out


def test_speakable_keeps_telugu_and_trims_at_sentence_boundary():
    text = "మొత్తం బడ్జెట్ 35000. " * 50
    out = to_speakable(text, max_chars=100)
    assert len(out) <= 100
    assert out.endswith(".")
    assert "బడ్జెట్" in out


def test_build_prompt_includes_vocabulary_within_limit():
    prompt = build_prompt("auto", ["Projects", "Budget", "Vendor Name"])
    assert "total budget ఎంత" in prompt
    assert "Projects" in prompt and "Vendor Name" in prompt
    long = build_prompt("auto", [f"Field{i}" for i in range(500)])
    assert len(long) <= 380
    assert "ఎంత" not in build_prompt("en", [])


@pytest.mark.parametrize(
    "text,segments,silent",
    [
        ("", [], True),
        ("...", [], True),
        ("Thank you.", [{"no_speech_prob": 0.4}], True),
        ("Thank you.", [{"no_speech_prob": 0.01}], False),
        ("total budget ఎంత?", [{"no_speech_prob": 0.9}], True),
        ("total budget ఎంత?", [{"no_speech_prob": 0.1}], False),
    ],
)
def test_looks_silent(text, segments, silent):
    assert looks_silent(text, segments, "prompt") is silent


def test_prompt_echo_is_treated_as_silence():
    prompt = build_prompt("auto", [])
    assert looks_silent("Telugu and English mixed conversation about spreadsheet data.", [], prompt)


def test_sniff_and_validate_audio():
    assert sniff_format(b"\x1aE\xdf\xa3....") == "webm"
    assert sniff_format(b"OggS....") == "ogg"
    assert sniff_format(b"\x00\x00\x00\x20ftypM4A ") == "mp4"
    wav = pcm_to_wav(b"\x00\x00" * 24000)
    assert sniff_format(wav) == "wav"
    assert wav_duration_seconds(wav) == pytest.approx(1.0)

    with pytest.raises(AudioValidationError) as empty:
        validate_audio(b"", 1000, 10)
    assert empty.value.error_code == "EMPTY_AUDIO"
    with pytest.raises(AudioValidationError) as big:
        validate_audio(b"\x1aE\xdf\xa3" + b"0" * 2000, 1000, 10)
    assert big.value.status_code == 413
    with pytest.raises(AudioValidationError) as bad:
        validate_audio(b"<html>not audio</html>", 1000, 10)
    assert bad.value.status_code == 415


def test_fold_stray_indic_letters_into_telugu():
    # Real Whisper output from a live test: Devanagari/Bengali letters inside Telugu words.
    raw = "ప्रोजেक्स శीट లो total budget ఎంత? pending tasks ఎంణ్ని ఉన్నాయि?"
    folded = fold_indic_into_telugu(raw)
    assert folded == "ప్రోజేక్స శీట లో total budget ఎంత? pending tasks ఎంణ్ని ఉన్నాయి?"
    assert all(not (0x0900 <= ord(c) <= 0x09FF) for c in folded)


def test_fold_leaves_real_hindi_and_english_alone():
    assert fold_indic_into_telugu("कुल बजट कितना है?") == "कुल बजट कितना है?"
    assert fold_indic_into_telugu("What is the total?") == "What is the total?"
