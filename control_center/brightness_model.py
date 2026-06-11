"""MacUX Control Center — screen brightness model.

BrightnessState is a pure dataclass.
BrightnessManager reads and writes brightness via:
  1. /sys/class/backlight/<device>/ (direct, preferred — requires udev rule)
  2. `brightnessctl` subprocess (fallback)

Both backends present a 0–100 percent interface.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKLIGHT_DIR = Path("/sys/class/backlight")


@dataclass
class BrightnessState:
    """Snapshot of screen brightness."""

    level: int        # 0–100 percent
    available: bool   # False when no backlight device is found

    def icon_name(self) -> str:
        if not self.available:
            return "display-brightness-symbolic"
        if self.level > 66:
            return "display-brightness-high-symbolic"
        if self.level > 33:
            return "display-brightness-medium-symbolic"
        return "display-brightness-low-symbolic"


class BrightnessManager:
    """
    Reads and sets screen brightness.

    Usage::

        mgr = BrightnessManager()
        state = mgr.get_state()
        mgr.set_level(70)
    """

    def __init__(self) -> None:
        self._device_path: Path | None = self._find_device()
        self._max_brightness: int = self._read_max()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_state(self) -> BrightnessState:
        level = self._read_level()
        return BrightnessState(level=level, available=self._device_path is not None or self._has_brightnessctl())

    def set_level(self, percent: int) -> None:
        """Set brightness to *percent* (0–100, clamped)."""
        percent = max(0, min(100, percent))
        if self._device_path and self._max_brightness > 0:
            raw = round(percent / 100 * self._max_brightness)
            try:
                (self._device_path / "brightness").write_text(str(raw))
                return
            except PermissionError:
                logger.debug("BrightnessManager: sysfs write denied, trying brightnessctl")
        self._set_via_brightnessctl(percent)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _find_device(self) -> Path | None:
        if not _BACKLIGHT_DIR.exists():
            return None
        try:
            devices = sorted(_BACKLIGHT_DIR.iterdir())
            return devices[0] if devices else None
        except Exception:
            return None

    def _read_max(self) -> int:
        if self._device_path is None:
            return 0
        try:
            return int((self._device_path / "max_brightness").read_text().strip())
        except Exception:
            return 0

    def _read_level(self) -> int:
        if self._device_path and self._max_brightness > 0:
            try:
                raw = int((self._device_path / "brightness").read_text().strip())
                return round(raw / self._max_brightness * 100)
            except Exception:
                pass
        return self._read_via_brightnessctl()

    def _read_via_brightnessctl(self) -> int:
        try:
            out = subprocess.check_output(
                ["brightnessctl", "get"], stderr=subprocess.DEVNULL, text=True
            ).strip()
            max_out = subprocess.check_output(
                ["brightnessctl", "max"], stderr=subprocess.DEVNULL, text=True
            ).strip()
            raw, maximum = int(out), int(max_out)
            return round(raw / maximum * 100) if maximum else 50
        except Exception:
            return 50

    def _set_via_brightnessctl(self, percent: int) -> None:
        try:
            subprocess.run(
                ["brightnessctl", "set", f"{percent}%"],
                check=False, capture_output=True
            )
        except FileNotFoundError:
            logger.debug("BrightnessManager: brightnessctl not found")

    @staticmethod
    def _has_brightnessctl() -> bool:
        try:
            subprocess.run(["brightnessctl", "--version"],
                           check=False, capture_output=True)
            return True
        except FileNotFoundError:
            return False
