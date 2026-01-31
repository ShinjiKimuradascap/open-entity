---
name: voice_synthesis
description: Cross-platform text-to-speech synthesis skill with auto-detection
tools:
  - speak
  - list_voices
  - detect_platform
---

# voice_synthesis

Cross-platform text-to-speech synthesis skill that automatically detects the operating system and uses the appropriate speech engine.

## Supported Platforms

| Platform | Engine | Voice Support |
|----------|--------|---------------|
| macOS | say | Native voices (Kyoko, etc.) |
| Linux | espeak or spd-say | Multiple languages |
| Other | print fallback | Text output only |

## Tools

- speak(text, voice, rate) - Synthesize speech from text
- list_voices() - List available voices for the current platform
- detect_platform() - Detect current platform and available engine

## Usage Example

    from skills.voice_synthesis import speak, list_voices
    speak("Hello, world!")
    speak("Hello!", voice="Kyoko", rate=180)
    voices = list_voices()

## Environment Variables

- VOICE_SYNTHESIS_ENGINE: Override auto-detection
- VOICE_DEFAULT_VOICE: Set default voice name  
- VOICE_DEFAULT_RATE: Set default speech rate
