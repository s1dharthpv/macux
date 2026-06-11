"""MacUX Control Center — WiFi model.

WiFiNetwork is a pure dataclass (no GTK).
WifiManager wraps libnm (NM.Client) to scan, list, connect, and disconnect.
Gracefully degrades when libnm is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# NM.80211ApSecurityFlags bit that indicates WPA/RSN security
_NM_802_11_AP_SEC_KEY_MGMT_PSK = 0x00000100
_NM_802_11_AP_SEC_KEY_MGMT_802_1X = 0x00000200


@dataclass
class WiFiNetwork:
    """Snapshot of a visible access point."""

    ssid: str
    bssid: str
    signal: int       # 0–100 (NM strength)
    secured: bool
    connected: bool

    def icon_name(self) -> str:
        if self.signal > 80:
            return "network-wireless-signal-excellent-symbolic"
        if self.signal > 55:
            return "network-wireless-signal-good-symbolic"
        if self.signal > 30:
            return "network-wireless-signal-ok-symbolic"
        return "network-wireless-signal-weak-symbolic"

    def format_signal(self) -> str:
        return f"{self.signal}%"


class WifiManager:
    """
    Manages WiFi via libnm (NetworkManager GObject introspection bindings).

    Usage::

        mgr = WifiManager(on_networks_changed=lambda nets: rebuild_list(nets))
        mgr.start()
    """

    def __init__(
        self,
        on_networks_changed: Callable[[list[WiFiNetwork]], None] | None = None,
    ) -> None:
        self._on_networks_changed = on_networks_changed
        self._client = None
        self._wifi_device = None

    def start(self) -> None:
        try:
            self._connect()
        except Exception as exc:
            logger.warning("WifiManager: libnm unavailable: %s", exc)

    def is_available(self) -> bool:
        return self._wifi_device is not None

    def is_enabled(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.get_wireless_enabled())
        except Exception:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if self._client is None:
            return
        try:
            self._client.wireless_set_enabled(enabled)
        except Exception as exc:
            logger.warning("WifiManager: set_enabled error: %s", exc)

    def get_networks(self) -> list[WiFiNetwork]:
        if self._wifi_device is None:
            return []
        try:
            return self._collect_networks()
        except Exception as exc:
            logger.debug("WifiManager: get_networks error: %s", exc)
            return []

    def connect(self, ssid: str, password: str = "") -> None:
        if self._client is None or self._wifi_device is None:
            return
        try:
            import gi
            gi.require_version("NM", "1.0")
            from gi.repository import NM, GLib
            # Find matching AP
            ap = self._find_ap(ssid)
            if ap is None:
                logger.warning("WifiManager: SSID %r not found", ssid)
                return
            conn = NM.SimpleConnection.new()
            s_wifi = NM.SettingWireless.new()
            s_wifi.set_property(NM.SETTING_WIRELESS_SSID,
                                GLib.Bytes.new(ssid.encode()))
            conn.add_setting(s_wifi)
            if password:
                s_wsec = NM.SettingWirelessSecurity.new()
                s_wsec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk")
                s_wsec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
                conn.add_setting(s_wsec)
            self._client.add_and_activate_connection_async(
                conn, self._wifi_device, ap.get_path(), None, None, None
            )
        except Exception as exc:
            logger.warning("WifiManager: connect error: %s", exc)

    def disconnect(self) -> None:
        if self._client is None or self._wifi_device is None:
            return
        try:
            ac = self._wifi_device.get_active_connection()
            if ac:
                self._client.deactivate_connection_async(ac, None, None, None)
        except Exception as exc:
            logger.warning("WifiManager: disconnect error: %s", exc)

    def request_scan(self) -> None:
        if self._wifi_device is None:
            return
        try:
            self._wifi_device.request_scan(None)
        except Exception as exc:
            logger.debug("WifiManager: scan error: %s", exc)

    def get_current_ssid(self) -> str:
        if self._wifi_device is None:
            return ""
        try:
            ap = self._wifi_device.get_active_access_point()
            if ap:
                ssid_bytes = ap.get_ssid()
                return ssid_bytes.get_data().decode("utf-8", errors="replace") if ssid_bytes else ""
        except Exception:
            pass
        return ""

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        import gi
        gi.require_version("NM", "1.0")
        from gi.repository import NM
        self._client = NM.Client.new(None)
        for dev in self._client.get_devices():
            if dev.get_device_type() == NM.DeviceType.WIFI:
                self._wifi_device = dev
                dev.connect("access-point-added", lambda *_: self._emit_networks())
                dev.connect("access-point-removed", lambda *_: self._emit_networks())
                break

    def _collect_networks(self) -> list[WiFiNetwork]:
        active_ap = self._wifi_device.get_active_access_point()
        active_bssid = ""
        if active_ap:
            active_bssid = active_ap.get_bssid() or ""

        seen_ssids: set[str] = set()
        networks: list[WiFiNetwork] = []
        for ap in self._wifi_device.get_access_points():
            ssid_bytes = ap.get_ssid()
            if not ssid_bytes:
                continue
            ssid = ssid_bytes.get_data().decode("utf-8", errors="replace")
            if not ssid or ssid in seen_ssids:
                continue
            seen_ssids.add(ssid)
            rsn = ap.get_rsn_flags()
            wpa = ap.get_wpa_flags()
            secured = bool(rsn or wpa)
            networks.append(WiFiNetwork(
                ssid=ssid,
                bssid=ap.get_bssid() or "",
                signal=int(ap.get_strength()),
                secured=secured,
                connected=ap.get_bssid() == active_bssid,
            ))
        networks.sort(key=lambda n: (-n.connected, -n.signal))
        return networks

    def _find_ap(self, ssid: str):
        for ap in self._wifi_device.get_access_points():
            ssid_bytes = ap.get_ssid()
            if not ssid_bytes:
                continue
            if ssid_bytes.get_data().decode("utf-8", errors="replace") == ssid:
                return ap
        return None

    def _emit_networks(self) -> None:
        if self._on_networks_changed:
            nets = self.get_networks()
            try:
                from gi.repository import GLib
                GLib.idle_add(lambda: self._on_networks_changed(nets) or False)
            except ImportError:
                self._on_networks_changed(nets)
