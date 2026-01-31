"""Cross-platform text-to-speech synthesis skill.

This module provides text-to-speech functionality with automatic platform
detection. Supports macOS (say), Linux (espeak/spd-say), with fallback to print.

Examples:
    >>> from voice_synthesis import speak, list_voices
    >>> speak("Hello, world!")
    >>> speak("Hello!", voice="Kyoko", rate=180)
    >>> voices = list_voices()
"""

import os
import platform
import shutil
import subprocess
from enum import Enum
from typing import List, Optional


class PlatformEngine(Enum):
    """Supported TTS engines by platform."""
    SAY = "say"           # macOS
    ESPEAK = "espeak"     # Linux
    SPD_SAY = "spd-say"   # Linux (Speech Dispatcher)
    PRINT = "print"       # Fallback


# Platform detection cache
_platform_cache: Optional[str] = None
_engine_cache: Optional[PlatformEngine] = None


def detect_platform() -> dict:
    """Detect the current platform and available TTS engine.
    
    Returns:
        Dictionary with platform info and detected engine.
        
    Example:
        >>> info = detect_platform()
        >>> print(info['engine'])  # 'say', 'espeak', 'spd-say', or 'print'
    """
    system = platform.system()
    detected_engine = None
    engine_path = None
    
    # Check for environment override
    env_engine = os.environ.get("VOICE_SYNTHESIS_ENGINE")
    if env_engine:
        engine_map = {
            "say": PlatformEngine.SAY,
            "espeak": PlatformEngine.ESPEAK,
            "spd-say": PlatformEngine.SPD_SAY,
            "print": PlatformEngine.PRINT,
        }
        detected_engine = engine_map.get(env_engine.lower(), PlatformEngine.PRINT)
        if detected_engine != PlatformEngine.PRINT:
            engine_path = shutil.which(detected_engine.value)
    
    # Auto-detect if no override
    if not detected_engine:
        if system == "Darwin":  # macOS
            engine_path = shutil.which("say")
            if engine_path:
                detected_engine = PlatformEngine.SAY
        elif system == "Linux":
            # Prefer espeak, fallback to spd-say
            engine_path = shutil.which("espeak")
            if engine_path:
                detected_engine = PlatformEngine.ESPEAK
            else:
                engine_path = shutil.which("spd-say")
                if engine_path:
                    detected_engine = PlatformEngine.SPD_SAY
        
        # Fallback to print if no TTS engine found
        if not detected_engine:
            detected_engine = PlatformEngine.PRINT
    
    return {
        "system": system,
        "engine": detected_engine.value if detected_engine else "print",
        "engine_path": engine_path,
        "is_fallback": detected_engine == PlatformEngine.PRINT,
    }


def _get_engine() -> PlatformEngine:
    """Get cached engine or detect platform.
    
    Returns:
        PlatformEngine enum for the detected/specified engine.
    """
    global _engine_cache
    if _engine_cache is None:
        info = detect_platform()
        _engine_cache = PlatformEngine(info["engine"])
    return _engine_cache


def speak(
    text: str,
    voice: Optional[str] = None,
    rate: Optional[int] = None
) -> bool:
    """Synthesize speech from text using platform-appropriate engine.
    
    Automatically detects the platform and uses the available TTS engine:
    - macOS: Uses 'say' command with voice support
    - Linux: Uses 'espeak' or 'spd-say'
    - Other: Falls back to printing the text
    
    Args:
        text: The text to speak.
        voice: Voice name (platform-specific). For macOS, e.g., 'Kyoko', 'Alex'.
               Defaults to environment variable VOICE_DEFAULT_VOICE or system default.
        rate: Speech rate. macOS: words per minute (default ~175).
              Linux: espeak speed (80-450, default 175).
              Defaults to environment variable VOICE_DEFAULT_RATE.
    
    Returns:
        True if speech synthesis was attempted, False on error.
        
    Example:
        >>> speak("Hello, world!")
        True
        >>> speak("Hello!", voice="Kyoko", rate=180)
        True
        >>> speak("Error occurred", voice="Fred")
        True
    """
    if not text:
        print("[voice_synthesis] Warning: Empty text provided")
        return False
    
    engine = _get_engine()
    
    # Get defaults from environment
    default_voice = os.environ.get("VOICE_DEFAULT_VOICE")
    default_rate = os.environ.get("VOICE_DEFAULT_RATE")
    
    voice = voice or default_voice
    if rate is None and default_rate:
        try:
            rate = int(default_rate)
        except ValueError:
            pass
    
    try:
        if engine == PlatformEngine.SAY:
            return _speak_say(text, voice, rate)
        elif engine == PlatformEngine.ESPEAK:
            return _speak_espeak(text, voice, rate)
        elif engine == PlatformEngine.SPD_SAY:
            return _speak_spd_say(text, voice, rate)
        else:
            return _speak_print(text, voice, rate)
    except Exception as e:
        print(f"[voice_synthesis] Error: {e}")
        return False


def _speak_say(text: str, voice: Optional[str], rate: Optional[int]) -> bool:
    """Use macOS 'say' command."""
    cmd = ["say"]
    
    if voice:
        cmd.extend(["-v", voice])
    if rate:
        cmd.extend(["-r", str(rate)])
    
    cmd.append(text)
    
    subprocess.run(cmd, check=False, capture_output=True)
    print(f"[🔊 macOS say{f' -v {voice}' if voice else ''}] {text[:60]}{'...' if len(text) > 60 else ''}")
    return True


def _speak_espeak(text: str, voice: Optional[str], rate: Optional[int]) -> bool:
    """Use Linux 'espeak' command."""
    cmd = ["espeak"]
    
    if voice:
        cmd.extend(["-v", voice])
    if rate:
        cmd.extend(["-s", str(rate)])
    
    cmd.append(text)
    
    subprocess.run(cmd, check=False, capture_output=True)
    print(f"[🔊 espeak{f' -v {voice}' if voice else ''}] {text[:60]}{'...' if len(text) > 60 else ''}")
    return True


def _speak_spd_say(text: str, voice: Optional[str], rate: Optional[int]) -> bool:
    """Use Linux 'spd-say' command (Speech Dispatcher)."""
    cmd = ["spd-say"]
    
    if voice:
        cmd.extend(["-o", voice])  # Output module/voice
    if rate:
        # spd-say uses percentage (-100 to 100, 0 is default)
        # Convert from wpm-like value to percentage
        rate_pct = min(100, max(-100, (rate - 175) // 2))
        cmd.extend(["-r", str(rate_pct)])
    
    cmd.append(text)
    
    subprocess.run(cmd, check=False, capture_output=True)
    print(f"[🔊 spd-say{f' -o {voice}' if voice else ''}] {text[:60]}{'...' if len(text) > 60 else ''}")
    return True


def _speak_print(text: str, voice: Optional[str], rate: Optional[int]) -> bool:
    """Fallback to printing text."""
    voice_info = f" (voice: {voice})" if voice else ""
    rate_info = f" (rate: {rate})" if rate else ""
    print(f"[🔊 TTS FALLBACK{voice_info}{rate_info}] {text}")
    print("  (Install 'espeak' or 'spd-say' for actual speech output)")
    return True


def list_voices() -> List[dict]:
    """List available voices for the current platform.
    
    Returns:
        List of voice dictionaries with 'name' and optional 'language'.
        
    Example:
        >>> voices = list_voices()
        >>> print(voices[0]['name'])
        'Kyoko'
    """
    engine = _get_engine()
    
    try:
        if engine == PlatformEngine.SAY:
            return _list_voices_say()
        elif engine == PlatformEngine.ESPEAK:
            return _list_voices_espeak()
        elif engine == PlatformEngine.SPD_SAY:
            return _list_voices_spd_say()
        else:
            return [{"name": "default", "language": "N/A", "note": "Print fallback - no voices available"}]
    except Exception as e:
        print(f"[voice_synthesis] Error listing voices: {e}")
        return []


def _list_voices_say() -> List[dict]:
    """List macOS say voices."""
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            text=True,
            check=False
        )
        voices = []
        for line in result.stdout.splitlines():
            # Format: VoiceName  lang  # Description
            parts = line.split(None, 2)
            if len(parts) >= 2:
                voices.append({
                    "name": parts[0],
                    "language": parts[1],
                    "description": parts[2].lstrip("# ") if len(parts) > 2 else ""
                })
        return voices
    except Exception:
        # Return common macOS voices as fallback
        return [
            {"name": "Alex", "language": "en_US", "description": "Default English"},
            {"name": "Kyoko", "language": "ja_JP", "description": "Japanese"},
            {"name": "Otoya", "language": "ja_JP", "description": "Japanese"},
            {"name": "Samantha", "language": "en_US", "description": "English"},
            {"name": "Victoria", "language": "en_US", "description": "English"},
        ]


def _list_voices_espeak() -> List[dict]:
    """List espeak voices."""
    try:
        result = subprocess.run(
            ["espeak", "--voices"],
            capture_output=True,
            text=True,
            check=False
        )
        voices = []
        lines = result.stdout.splitlines()
        # Skip header line
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                voices.append({
                    "name": parts[1],
                    "language": parts[2] if len(parts) > 2 else "unknown",
                    "description": " ".join(parts[3:]) if len(parts) > 3 else ""
                })
        return voices
    except Exception:
        return [
            {"name": "en", "language": "en", "description": "English"},
            {"name": "en-us", "language": "en-us", "description": "US English"},
            {"name": "ja", "language": "ja", "description": "Japanese"},
        ]


def _list_voices_spd_say() -> List[dict]:
    """List spd-say output modules."""
    try:
        result = subprocess.run(
            ["spd-say", "-o", "?"],
            capture_output=True,
            text=True,
            check=False
        )
        modules = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("NAME"):
                modules.append({
                    "name": line.split()[0] if line.split() else line,
                    "language": "varies",
                    "description": line
                })
        return modules
    except Exception:
        return [
            {"name": "default", "language": "system", "description": "Default module"},
            {"name": "espeak", "language": "varies", "description": "eSpeak module"},
        ]


def set_voice(voice_name: str) -> None:
    """Set the default voice for subsequent speak() calls.
    
    This sets the VOICE_DEFAULT_VOICE environment variable for the current session.
    
    Args:
        voice_name: Name of the voice to use as default.
        
    Example:
        >>> set_voice("Kyoko")
        >>> speak("Hello")  # Uses Kyoko voice
    """
    os.environ["VOICE_DEFAULT_VOICE"] = voice_name


def set_rate(rate: int) -> None:
    """Set the default speech rate for subsequent speak() calls.
    
    Args:
        rate: Speech rate (words per minute for say, speed for espeak).
        
    Example:
        >>> set_rate(200)  # Faster speech
        >>> speak("Hello")  # Uses faster rate
    """
    os.environ["VOICE_DEFAULT_RATE"] = str(rate)


# Example usage and self-test
if __name__ == "__main__":
    print("=" * 60)
    print("Voice Synthesis Skill - Self Test")
    print("=" * 60)
    
    # Platform detection
    info = detect_platform()
    print(f"\n📍 Platform: {info['system']}")
    print(f"🔧 Engine: {info['engine']}")
    print(f"📁 Engine Path: {info['engine_path'] or 'N/A'}")
    print(f"⚠️  Fallback Mode: {info['is_fallback']}")
    
    # List voices
    print("\n📋 Available Voices:")
    voices = list_voices()
    for v in voices[:5]:  # Show first 5
        print(f"   - {v['name']} ({v.get('language', 'N/A')})")
    if len(voices) > 5:
        print(f"   ... and {len(voices) - 5} more")
    
    # Test speak
    print("\n🔊 Testing speak():")
    
    # Basic test
    print("\n1. Basic speak:")
    speak("Hello, this is a voice synthesis test.")
    
    # With voice (if on macOS)
    if info['system'] == "Darwin":
        print("\n2. With Japanese voice (Kyoko):")
        speak("こんにちは。これはテストです。", voice="Kyoko")
        
        print("\n3. With different rate (fast):")
        speak("This is spoken at a faster rate.", rate=200)
    
    # Test environment variable
    print("\n4. Testing environment variable override:")
    os.environ["VOICE_SYNTHESIS_ENGINE"] = "print"
    import voice_synthesis as vs
    vs._engine_cache = None  # Reset cache via module reference
    speak("This should use print fallback due to env override.")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
