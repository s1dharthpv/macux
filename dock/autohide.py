"""MacUX Dock — auto-hide state machine.

Manages dock visibility based on cursor proximity and window overlap.
Pure state machine — no GTK dependencies. Drives animations in DockWindow.

States
------
  SHOWN       — dock fully visible
  HIDING      — hide timer is running (cursor left, waiting to confirm)
  HIDDEN      — dock fully hidden (only a 2 px edge strip is visible)
  SHOWING     — show animation in progress

Transitions
-----------
  SHOWN + cursor_left  → HIDING  (start hide_delay timer)
  HIDING + cursor_entered → SHOWN  (cancel timer)
  HIDING + timer_fired → HIDDEN
  HIDDEN + cursor_entered → SHOWING (immediate)
  SHOWING + animation_done → SHOWN
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)

HideCallback = Callable[[], None]
ShowCallback = Callable[[], None]


class AutoHideState(Enum):
    SHOWN = auto()
    HIDING = auto()
    HIDDEN = auto()
    SHOWING = auto()


class AutoHideController:
    """
    Auto-hide state machine for the MacUX Dock.

    Callers drive the state machine by calling:
      - cursor_entered()   — cursor moved into dock bounds (or edge strip)
      - cursor_left()      — cursor moved out of dock bounds
      - animation_done()   — show/hide animation finished
      - timer_tick()       — called at ~20 Hz while HIDING to check timeout

    Register callbacks to react to show/hide decisions:
      - on_show(cb)  — called when dock should become visible
      - on_hide(cb)  — called when dock should become hidden
    """

    def __init__(
        self,
        enabled: bool = True,
        hide_delay: float = 0.5,
        show_delay: float = 0.1,
    ) -> None:
        self._enabled = enabled
        self._hide_delay = hide_delay
        self._show_delay = show_delay
        self._state = AutoHideState.SHOWN
        self._hide_elapsed: float = 0.0
        self._show_elapsed: float = 0.0
        self._on_show: list[ShowCallback] = []
        self._on_hide: list[HideCallback] = []

    # ── Configuration ──────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._enabled == value:
            return
        self._enabled = value
        if not value:
            # Disabling auto-hide → force show
            self._transition(AutoHideState.SHOWN)
            self._fire_show()

    @property
    def state(self) -> AutoHideState:
        return self._state

    # ── Event drivers ──────────────────────────────────────────────────────────

    def cursor_entered(self) -> None:
        """Call when the cursor enters the dock's visible bounds."""
        if not self._enabled:
            return
        if self._state in (AutoHideState.HIDING, AutoHideState.HIDDEN):
            self._hide_elapsed = 0.0
            self._show_elapsed = 0.0
            self._transition(AutoHideState.SHOWING)
            self._fire_show()

    def cursor_left(self) -> None:
        """Call when the cursor leaves the dock bounds."""
        if not self._enabled:
            return
        if self._state == AutoHideState.SHOWN:
            self._hide_elapsed = 0.0
            self._transition(AutoHideState.HIDING)

    def animation_done(self) -> None:
        """Call when a show or hide animation completes."""
        if self._state == AutoHideState.SHOWING:
            self._transition(AutoHideState.SHOWN)
        elif self._state == AutoHideState.HIDING:
            self._transition(AutoHideState.HIDDEN)

    def timer_tick(self, delta: float) -> None:
        """
        Advance internal timers.

        Args:
            delta: seconds elapsed since last tick.
        """
        if self._state == AutoHideState.HIDING:
            self._hide_elapsed += delta
            if self._hide_elapsed >= self._hide_delay:
                self._transition(AutoHideState.HIDDEN)
                self._fire_hide()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_show(self, callback: ShowCallback) -> None:
        self._on_show.append(callback)

    def on_hide(self, callback: HideCallback) -> None:
        self._on_hide.append(callback)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _transition(self, new_state: AutoHideState) -> None:
        if new_state != self._state:
            logger.debug("AutoHide: %s → %s", self._state.name, new_state.name)
            self._state = new_state

    def _fire_show(self) -> None:
        for cb in self._on_show:
            try:
                cb()
            except Exception:
                logger.exception("AutoHide show callback raised")

    def _fire_hide(self) -> None:
        for cb in self._on_hide:
            try:
                cb()
            except Exception:
                logger.exception("AutoHide hide callback raised")
