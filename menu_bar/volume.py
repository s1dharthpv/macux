"""MacUX Menu Bar — volume state + PulseAudio monitor.

VolumeState is a pure dataclass. VolumeMonitor uses pulsectl in a daemon
thread; it calls on_change on the GLib main thread via GLib.idle_add.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Thread
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class VolumeState:
    """Snapshot of the default PulseAudio sink."""

    level: float     # 0.0–1.0  (may exceed 1.0 for amplified volume)
    muted: bool
    sink_name: str   # human-readable sink description

    @property
    def percent(self) -> int:
        """Volume as integer percentage (0–150+)."""
        return round(self.level * 100)

    def icon_name(self) -> str:
        if self.muted or self.level == 0.0:
            return "audio-volume-muted-symbolic"
        if self.level < 0.34:
            return "audio-volume-low-symbolic"
        if self.level < 0.67:
            return "audio-volume-medium-symbolic"
        return "audio-volume-high-symbolic"

    def format_label(self) -> str:
        if self.muted:
            return "Muted"
        return f"{self.percent}%"

    def format_tooltip(self) -> str:
        base = f"Volume: {self.percent}%"
        if self.muted:
            base = f"Volume: Muted ({self.percent}%)"
        if self.sink_name:
            base += f"\n{self.sink_name}"
        return base


class VolumeMonitor:
    """
    Monitors the default PulseAudio sink via pulsectl.

    Calls *on_change* whenever volume or mute state changes.  If pulsectl
    is unavailable, start() is a no-op and get_state() returns a default.

    Usage::

        monitor = VolumeMonitor(on_change=lambda s: print(s.format_label()))
        monitor.start()
    """

    def __init__(self, on_change: Callable[[VolumeState], None]) -> None:
        self._on_change = on_change
        self._state = VolumeState(level=1.0, muted=False, sink_name="")

    def start(self) -> None:
        try:
            import pulsectl  # noqa: F401
        except ImportError:
            logger.warning("VolumeMonitor: pulsectl not installed — volume indicator disabled")
            return
        t = Thread(target=self._watch_loop, daemon=True, name="macux-volume-monitor")
        t.start()

    def get_state(self) -> VolumeState:
        return self._state

    def set_volume(self, level: float) -> None:
        """Set master volume to *level* (0.0–1.0; clamped)."""
        level = max(0.0, min(1.5, level))
        try:
            import pulsectl
            with pulsectl.Pulse("macux-vol-set") as pulse:
                sinks = pulse.sink_list()
                if sinks:
                    pulse.volume_set_all_chans(sinks[0], level)
        except Exception as exc:
            logger.warning("VolumeMonitor: set_volume error: %s", exc)

    def toggle_mute(self) -> None:
        """Toggle mute on the default sink."""
        try:
            import pulsectl
            with pulsectl.Pulse("macux-mute") as pulse:
                sinks = pulse.sink_list()
                if sinks:
                    pulse.mute(sinks[0], not sinks[0].mute)
        except Exception as exc:
            logger.warning("VolumeMonitor: toggle_mute error: %s", exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _watch_loop(self) -> None:
        try:
            import pulsectl
            with pulsectl.Pulse("macux-vol-watch") as pulse:
                self._read_state(pulse)
                pulse.event_mask_set("sink")
                pulse.event_callback_set(lambda _e: self._read_state(pulse))
                pulse.event_listen(timeout=None)
        except Exception as exc:
            logger.warning("VolumeMonitor: watch loop exited: %s", exc)

    def _read_state(self, pulse) -> None:
        try:
            sinks = pulse.sink_list()
            if not sinks:
                return
            sink = sinks[0]
            level = pulse.volume_get_all_chans(sink)
            new_state = VolumeState(
                level=float(level),
                muted=bool(sink.mute),
                sink_name=sink.description or sink.name,
            )
            self._state = new_state
            try:
                from gi.repository import GLib
                GLib.idle_add(lambda: self._on_change(new_state) or False)
            except ImportError:
                self._on_change(new_state)
        except Exception as exc:
            logger.debug("VolumeMonitor: read state error: %s", exc)
