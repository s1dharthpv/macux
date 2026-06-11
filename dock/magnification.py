"""MacUX Dock — icon magnification controller.

Implements macOS-style dock magnification:
  - Icons near the cursor grow proportionally
  - Uses a raised-cosine envelope for smooth falloff
  - Animates smoothly toward target sizes (lerp at ~60 fps)

Pure math — no GTK dependencies. Consumed by DockWindow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass
class MagnificationConfig:
    """Tunable magnification parameters."""

    base_size: int = 48        # icon size when cursor is far away (px)
    max_size: int = 72         # icon size at peak magnification (px)
    radius: int = 100          # cursor influence radius (px)
    lerp_speed: float = 0.25   # fraction to move per frame (0–1)

    def __post_init__(self) -> None:
        if self.base_size <= 0:
            raise ValueError(f"base_size must be > 0, got {self.base_size}")
        if self.max_size < self.base_size:
            raise ValueError("max_size must be >= base_size")
        if self.radius <= 0:
            raise ValueError(f"radius must be > 0, got {self.radius}")
        if not (0.0 < self.lerp_speed <= 1.0):
            raise ValueError(f"lerp_speed must be in (0, 1], got {self.lerp_speed}")


class MagnificationController:
    """
    Computes per-icon display sizes based on cursor proximity.

    Usage::

        ctrl = MagnificationController(MagnificationConfig(...))

        # Call on every cursor-motion event (icon_centers in widget coords):
        targets = ctrl.compute_target_sizes(cursor_x=150, icon_centers=[48, 96, 144])

        # Call at ~60 fps to animate:
        ctrl.current_sizes  # read these and resize icons
        ctrl.step()         # lerp current → target

        # On cursor leave:
        ctrl.reset()        # snap all back to base_size immediately
    """

    def __init__(self, config: MagnificationConfig | None = None) -> None:
        self._cfg = config or MagnificationConfig()
        self._targets: list[float] = []
        self._current: list[float] = []
        self._enabled: bool = True

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def current_sizes(self) -> list[float]:
        """Current animated sizes to apply to icons (px)."""
        return list(self._current)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self.reset()

    def compute_target_sizes(
        self,
        cursor_x: float,
        icon_centers: Sequence[float],
    ) -> list[float]:
        """
        Compute target sizes for each icon given the cursor x-coordinate.

        Uses a raised-cosine envelope:
          factor(d) = cos²(π·d / (2·R))   if d ≤ R, else 0
          target(d) = base + (max − base) · factor(d)

        Args:
            cursor_x:     cursor x in dock-widget coordinates.
            icon_centers: x-coordinate of each icon's center.

        Returns:
            List of target pixel sizes, one per icon.
        """
        if not self._enabled:
            return [float(self._cfg.base_size)] * len(icon_centers)

        cfg = self._cfg
        targets: list[float] = []
        for center in icon_centers:
            d = abs(cursor_x - center)
            if d >= cfg.radius:
                targets.append(float(cfg.base_size))
            else:
                # Raised-cosine envelope: 1.0 at d=0, 0.0 at d=radius
                factor = math.cos(math.pi * d / (2.0 * cfg.radius)) ** 2
                size = cfg.base_size + (cfg.max_size - cfg.base_size) * factor
                targets.append(size)

        self._targets = targets

        # Initialise current if needed
        if len(self._current) != len(targets):
            self._current = [float(cfg.base_size)] * len(targets)

        return targets

    def step(self) -> bool:
        """
        Advance one animation frame (lerp current → target).

        Returns True if any icon is still animating (not yet at target).
        Call this at ~60 fps.
        """
        if not self._targets or not self._current:
            return False

        speed = self._cfg.lerp_speed
        still_moving = False
        for i, (cur, tgt) in enumerate(zip(self._current, self._targets)):
            delta = tgt - cur
            if abs(delta) < 0.5:
                self._current[i] = tgt
            else:
                self._current[i] = cur + delta * speed
                still_moving = True

        return still_moving

    def reset(self) -> None:
        """Immediately snap all icons back to base size (on cursor leave)."""
        base = float(self._cfg.base_size)
        self._targets = [base] * len(self._current)
        self._current = [base] * len(self._current)

    def resize(self, n_icons: int) -> None:
        """Resize internal arrays when the icon count changes."""
        base = float(self._cfg.base_size)
        self._targets = [base] * n_icons
        self._current = [base] * n_icons

    def icon_sizes_as_int(self) -> list[int]:
        """Return current sizes rounded to integers."""
        return [round(s) for s in self._current]
