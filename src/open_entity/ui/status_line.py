"""Ephemeral status line for Claude Code-style CLI display.

Prints a dimmed, overwrite-in-place status line below streaming text.
Designed for normal (non-pane, non-async) chat mode only.
"""
from __future__ import annotations

import sys
import time


class StatusLine:
    """Manages a single ephemeral line at the current cursor position.

    The status line is shown on a new line below the current output.
    When cleared, it erases itself by moving the cursor up and clearing
    the line, so streaming text can continue seamlessly.
    """

    def __init__(self) -> None:
        self._text: str = ""
        self._visible: bool = False
        self._start_time: float = 0.0

    @property
    def visible(self) -> bool:
        return self._visible

    def show(self, text: str, start_time: float | None = None) -> None:
        """Display or update the ephemeral status line."""
        if self._is_broken():
            return
        self.clear()
        self._text = text
        if start_time is not None:
            self._start_time = start_time
        elapsed = self._format_elapsed()
        display = f"{text} {elapsed}" if elapsed else text
        try:
            sys.stdout.write(f"\n\x1b[2m{display}\x1b[0m")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            return
        self._visible = True

    def clear(self) -> None:
        """Erase the ephemeral status line so output can continue cleanly."""
        if not self._visible:
            return
        if self._is_broken():
            self._visible = False
            return
        try:
            # Move cursor up 1 line, carriage return, clear to end of line
            sys.stdout.write("\x1b[1A\r\x1b[K")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            pass
        self._visible = False

    def reset(self) -> None:
        """Clear and reset all internal state."""
        self.clear()
        self._text = ""
        self._start_time = 0.0

    def _format_elapsed(self) -> str:
        if self._start_time <= 0:
            return ""
        secs = time.time() - self._start_time
        if secs < 60:
            return f"({secs:.1f}s)"
        mins = int(secs // 60)
        remaining = secs % 60
        return f"({mins}m {remaining:.0f}s)"

    @staticmethod
    def _is_broken() -> bool:
        try:
            from open_entity.core.runtime import StreamPrintState
            return StreamPrintState.broken
        except Exception:
            return False
