"""MacUX Menu Bar — battery state + UPower DBus monitor.

BatteryState is a pure dataclass with formatting methods.
BatteryMonitor connects to org.freedesktop.UPower on the system bus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# UPower device State enum values
_STATE_CHARGING      = 1
_STATE_DISCHARGING   = 2
_STATE_FULLY_CHARGED = 4
# UPower device Type enum value for battery
_DEVICE_TYPE_BATTERY = 2


@dataclass
class BatteryState:
    """Snapshot of the battery at a point in time."""

    percentage: float        # 0.0–100.0
    charging: bool
    fully_charged: bool
    time_remaining_sec: int  # seconds; 0 if unknown
    present: bool

    @classmethod
    def absent(cls) -> BatteryState:
        """Sentinel for no battery device."""
        return cls(
            percentage=0.0,
            charging=False,
            fully_charged=False,
            time_remaining_sec=0,
            present=False,
        )

    def icon_name(self) -> str:
        if not self.present:
            return "battery-missing-symbolic"
        if self.fully_charged:
            return "battery-full-charged-symbolic"
        p = self.percentage
        if self.charging:
            if p > 80: return "battery-full-charging-symbolic"
            if p > 40: return "battery-good-charging-symbolic"
            return "battery-low-charging-symbolic"
        # Discharging
        if p > 80: return "battery-full-symbolic"
        if p > 60: return "battery-good-symbolic"
        if p > 40: return "battery-medium-symbolic"
        if p > 20: return "battery-low-symbolic"
        return "battery-caution-symbolic"

    def format_label(self) -> str:
        if not self.present:
            return ""
        if self.fully_charged:
            return "100%"
        if self.charging:
            return f"⚡ {self.percentage:.0f}%"
        return f"{self.percentage:.0f}%"

    def format_tooltip(self) -> str:
        if not self.present:
            return "No battery detected"
        if self.fully_charged:
            return "Battery fully charged"
        status = "Charging" if self.charging else "Discharging"
        tip = f"{status}: {self.percentage:.0f}%"
        if self.time_remaining_sec > 0:
            total_min = self.time_remaining_sec // 60
            h, m = divmod(total_min, 60)
            if h:
                tip += f" — {h}h {m:02d}m remaining"
            else:
                tip += f" — {m}m remaining"
        return tip


class BatteryMonitor:
    """
    Polls org.freedesktop.UPower for battery info on the system bus.

    Usage::

        monitor = BatteryMonitor(on_change=lambda s: print(s.format_label()))
        monitor.start()
    """

    _UPOWER_BUS  = "org.freedesktop.UPower"
    _UPOWER_PATH = "/org/freedesktop/UPower"

    def __init__(self, on_change: Callable[[BatteryState], None]) -> None:
        self._on_change = on_change
        self._state = BatteryState.absent()

    def start(self) -> None:
        try:
            self._connect()
        except Exception as exc:
            logger.warning("BatteryMonitor: UPower unavailable: %s", exc)

    def get_state(self) -> BatteryState:
        return self._state

    def _connect(self) -> None:
        from dasbus.connection import SystemMessageBus
        bus = SystemMessageBus()
        upower = bus.get_proxy(self._UPOWER_BUS, self._UPOWER_PATH)
        for dev_path in upower.EnumerateDevices():
            dev = bus.get_proxy(self._UPOWER_BUS, dev_path)
            try:
                if int(dev.Type) == _DEVICE_TYPE_BATTERY:
                    self._refresh(dev)
                    dev.PropertiesChanged.connect(lambda *_: self._refresh(dev))
                    break
            except Exception:
                continue

    def _refresh(self, dev) -> None:
        try:
            state_val = int(dev.State)
            t_empty = int(dev.TimeToEmpty)
            t_full  = int(dev.TimeToFull)
            self._state = BatteryState(
                percentage=float(dev.Percentage),
                charging=state_val == _STATE_CHARGING,
                fully_charged=state_val == _STATE_FULLY_CHARGED,
                time_remaining_sec=t_empty if state_val == _STATE_DISCHARGING else t_full,
                present=bool(dev.IsPresent),
            )
            self._on_change(self._state)
        except Exception as exc:
            logger.debug("BatteryMonitor: refresh error: %s", exc)
