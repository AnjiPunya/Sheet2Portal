"""Voice assistant: speech-to-text -> existing chat orchestrator -> speakable reply (+ optional TTS).

Kept in its own package so it layers on top of ``app/services/ai`` without
modifying it: the chat tool-calling loop, providers and tools are reused
as-is, and voice-specific behaviour (reply language, brevity) is injected by
wrapping the provider (see ``style.py``).
"""
