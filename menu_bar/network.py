"""MacUX Menu Bar — network state + NetworkManager DBus monitor.

NetworkState is a pure dataclass with icon/label/tooltip methods.
NetworkMonitor connects to org.freedesktop.NetworkManager on the system bus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)

# NM state constant
_NM_STATE_CONNECTED_GLOBAL = 70
# NM device type for Wi-Fi
_NM_DEVICE_TYPE_WIFI = 2


class ConnectionType(Enum):
    NONE     = auto()
    WIFI     = auto()
    ETHERNET = auto()
    CELLULAR = auto()
    VPN      = auto()
    OTHER    = auto()


@dataclass
class NetworkState:
    """Snapshot of the active network connection."""

    connected: bool
    conn_type: ConnectionType = ConnectionType.NONE
    ssid: str = ""     # Wi-Fi SSID or ""
    signal: int = 0    # 0–100 (Wi-Fi RSSI), 100 (wired), 0 (none)

    def icon_name(self) -> str:
        if not self.connected:
            return "network-offline-symbolic"
        if self.conn_type == ConnectionType.ETHERNET:
            return "network-wired-symbolic"
        if self.conn_type == ConnectionType.WIFI:
            s = self.signal
            if s > 80: return "network-wireless-signal-excellent-symbolic"
            if s > 55: return "network-wireless-signal-good-symbolic"
            if s > 30: return "network-wireless-signal-ok-symbolic"
            return "network-wireless-signal-weak-symbolic"
        return "network-transmit-receive-symbolic"

    def format_label(self) -> str:
        """Return the SSID for Wi-Fi; empty for other types."""
        if self.connected and self.conn_type == ConnectionType.WIFI and self.ssid:
            return self.ssid
        return ""

    def format_tooltip(self) -> str:
        if not self.connected:
            return "Not connected"
        if self.conn_type == ConnectionType.ETHERNET:
            return "Connected via Ethernet"
        if self.conn_type == ConnectionType.WIFI:
            base = f"Wi-Fi: {self.ssid}" if self.ssid else "Wi-Fi"
            return f"{base} ({self.signal}%)"
        return "Connected"


class NetworkMonitor:
    """
    Watches org.freedesktop.NetworkManager on the system bus.

    Usage::

        monitor = NetworkMonitor(on_change=lambda s: print(s.icon_name()))
        monitor.start()
    """

    _NM_BUS  = "org.freedesktop.NetworkManager"
    _NM_PATH = "/org/freedesktop/NetworkManager"

    def __init__(self, on_change: Callable[[NetworkState], None]) -> None:
        self._on_change = on_change
        self._state = NetworkState(connected=False)
        self._bus = None

    def start(self) -> None:
        try:
            self._connect()
        except Exception as exc:
            logger.warning("NetworkMonitor: NetworkManager unavailable: %s", exc)

    def get_state(self) -> NetworkState:
        return self._state

    def _connect(self) -> None:
        from dasbus.connection import SystemMessageBus
        self._bus = SystemMessageBus()
        nm = self._bus.get_proxy(self._NM_BUS, self._NM_PATH)
        self._refresh(nm)
        nm.StateChanged.connect(lambda _state: self._refresh(nm))

    def _refresh(self, nm) -> None:
        try:
            connected = int(nm.State) == _NM_STATE_CONNECTED_GLOBAL
            if not connected:
                self._state = NetworkState(connected=False)
                self._on_change(self._state)
                return
            self._state = self._read_connection(nm)
            self._on_change(self._state)
        except Exception as exc:
            logger.debug("NetworkMonitor: refresh error: %s", exc)

    def _read_connection(self, nm) -> NetworkState:
        try:
            for ac_path in nm.ActiveConnections:
                ac = self._bus.get_proxy(self._NM_BUS, str(ac_path))
                ctype = str(ac.Type).lower()
                if "wifi" in ctype or "wireless" in ctype:
                    ssid, sig = self._wifi_details(nm)
                    return NetworkState(
                        connected=True,
                        conn_type=ConnectionType.WIFI,
                        ssid=ssid,
                        signal=sig,
                    )
                if "ethernet" in ctype:
                    return NetworkState(
                        connected=True,
                        conn_type=ConnectionType.ETHERNET,
                        signal=100,
                    )
        except Exception as exc:
            logger.debug("NetworkMonitor: active connection read error: %s", exc)
        return NetworkState(connected=True, conn_type=ConnectionType.OTHER, signal=100)

    def _wifi_details(self, nm) -> tuple[str, int]:
        try:
            for dev_path in nm.GetDevices():
                dev = self._bus.get_proxy(self._NM_BUS, str(dev_path))
                if int(dev.DeviceType) == _NM_DEVICE_TYPE_WIFI:
                    ap_path = str(dev.ActiveAccessPoint)
                    ap = self._bus.get_proxy(self._NM_BUS, ap_path)
                    ssid = bytes(ap.Ssid).decode("utf-8", errors="replace")
                    return ssid, int(ap.Strength)
        except Exception:
            pass
        return "", 0
