"""MacUX Control Center — audio (PulseAudio sink) model.

AudioSink is a pure dataclass.
AudioController wraps pulsectl to list sinks, set default sink,
adjust per-sink volume, and toggle mute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class AudioSink:
    """Snapshot of one PulseAudio sink."""

    index: int
    name: str
    description: str
    volume: float     # 0.0–1.5 (pulsectl normalised)
    muted: bool
    is_default: bool

    @property
    def percent(self) -> int:
        """Volume as integer percentage (0–150)."""
        return round(self.volume * 100)

    def icon_name(self) -> str:
        if self.muted or self.volume == 0.0:
            return "audio-volume-muted-symbolic"
        if self.volume < 0.34:
            return "audio-volume-low-symbolic"
        if self.volume < 0.67:
            return "audio-volume-medium-symbolic"
        return "audio-volume-high-symbolic"


class AudioController:
    """
    Lists and controls PulseAudio sinks via pulsectl.

    Calls *on_sinks_changed* whenever sink state changes.

    Usage::

        ctrl = AudioController(on_sinks_changed=lambda sinks: rebuild_ui(sinks))
        ctrl.start()
    """

    def __init__(
        self,
        on_sinks_changed: Callable[[list[AudioSink]], None] | None = None,
    ) -> None:
        self._on_sinks_changed = on_sinks_changed

    def start(self) -> None:
        pass  # no background thread needed; sinks read on demand

    def get_sinks(self) -> list[AudioSink]:
        try:
            import pulsectl
            with pulsectl.Pulse("macux-cc-sinks") as pulse:
                return self._collect_sinks(pulse)
        except Exception as exc:
            logger.debug("AudioController: get_sinks error: %s", exc)
            return []

    def set_default_sink(self, index: int) -> None:
        try:
            import pulsectl
            with pulsectl.Pulse("macux-cc-default") as pulse:
                sinks = pulse.sink_list()
                for s in sinks:
                    if s.index == index:
                        pulse.sink_default_set(s)
                        break
            self._emit_sinks()
        except Exception as exc:
            logger.warning("AudioController: set_default_sink error: %s", exc)

    def set_volume(self, index: int, level: float) -> None:
        """Set volume on sink *index* to *level* (0.0–1.5; clamped)."""
        level = max(0.0, min(1.5, level))
        try:
            import pulsectl
            with pulsectl.Pulse("macux-cc-vol") as pulse:
                for s in pulse.sink_list():
                    if s.index == index:
                        pulse.volume_set_all_chans(s, level)
                        break
            self._emit_sinks()
        except Exception as exc:
            logger.warning("AudioController: set_volume error: %s", exc)

    def set_muted(self, index: int, muted: bool) -> None:
        try:
            import pulsectl
            with pulsectl.Pulse("macux-cc-mute") as pulse:
                for s in pulse.sink_list():
                    if s.index == index:
                        pulse.mute(s, muted)
                        break
            self._emit_sinks()
        except Exception as exc:
            logger.warning("AudioController: set_muted error: %s", exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_sinks(pulse) -> list[AudioSink]:
        default_name = pulse.server_info().default_sink_name
        sinks: list[AudioSink] = []
        for s in pulse.sink_list():
            volume = pulse.volume_get_all_chans(s)
            sinks.append(AudioSink(
                index=s.index,
                name=s.name,
                description=s.description or s.name,
                volume=float(volume),
                muted=bool(s.mute),
                is_default=(s.name == default_name),
            ))
        sinks.sort(key=lambda s: (not s.is_default, s.description.lower()))
        return sinks

    def _emit_sinks(self) -> None:
        if self._on_sinks_changed:
            sinks = self.get_sinks()
            try:
                from gi.repository import GLib
                GLib.idle_add(lambda: self._on_sinks_changed(sinks) or False)
            except ImportError:
                self._on_sinks_changed(sinks)
