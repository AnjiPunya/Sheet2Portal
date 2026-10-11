"""Validation of uploaded audio clips (no decoding -- no ffmpeg dependency).

The format is identified from the file's magic bytes rather than trusting
the client's Content-Type, which browsers report inconsistently (e.g.
``audio/webm;codecs=opus`` vs ``video/webm``).
"""

import io
import struct
import wave
from dataclasses import dataclass


class AudioValidationError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


@dataclass
class AudioClip:
    data: bytes
    format: str  # file extension understood by the STT API: webm, ogg, mp4, wav, mp3, flac
    mime_type: str


_MIME_BY_FORMAT = {
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "mp4": "audio/mp4",
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
}


def sniff_format(data: bytes) -> str | None:
    if data[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def validate_audio(data: bytes, max_bytes: int, min_bytes: int) -> AudioClip:
    if not data or len(data) < min_bytes:
        raise AudioValidationError(422, "EMPTY_AUDIO", "No audio was recorded. Hold the mic button and speak, then try again.")
    if len(data) > max_bytes:
        raise AudioValidationError(
            413, "AUDIO_TOO_LARGE", f"Recording is too large ({len(data) // 1024} KB; limit {max_bytes // 1024} KB). Keep it shorter."
        )
    fmt = sniff_format(data)
    if fmt is None:
        raise AudioValidationError(
            415, "UNSUPPORTED_AUDIO_FORMAT", "Unsupported audio format. Use webm/opus, ogg, mp4/m4a, wav, mp3 or flac."
        )
    return AudioClip(data=data, format=fmt, mime_type=_MIME_BY_FORMAT[fmt])


def wav_duration_seconds(data: bytes) -> float | None:
    """Exact duration for WAV (cheap to read); None for compressed formats."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, struct.error, ZeroDivisionError):
        return None


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
