"""Voice synthesis skill for cross-platform text-to-speech.

This skill provides text-to-speech functionality with automatic platform detection.
Supports macOS (say), Linux (espeak/spd-say), with fallback to print.

Example:
    >>> from skills.voice_synthesis import speak, list_voices
    >>> speak("Hello, world!")
    >>> voices = list_voices()
    >>> speak("Hello!", voice="Kyoko", rate=180)
"""

from .voice_synthesis import (
    speak,
    list_voices,
    detect_platform,
    set_voice,
    set_rate,
    PlatformEngine,
)

__all__ = [
    "speak",
    "list_voices",
    "detect_platform",
    "set_voice",
    "set_rate",
    "PlatformEngine",
]

__version__ = "1.0.0"
