"""MacUX Control Center — Bluetooth model.

BluetoothDevice is a pure dataclass.
BluetoothManager connects to org.bluez on the system bus via dasbus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

_BLUEZ_BUS       = "org.bluez"
_BLUEZ_ADAPTER   = "org.bluez.Adapter1"
_BLUEZ_DEVICE    = "org.bluez.Device1"
_ADAPTER_PATH    = "/org/bluez/hci0"
_OBJECT_MANAGER  = "org.freedesktop.DBus.ObjectManager"

# Bluetooth Class-of-Device major classes (bits 8–12)
_COD_AUDIO   = 0x04
_COD_INPUT   = 0x05
_COD_PHONE   = 0x02


@dataclass
class BluetoothDevice:
    """Snapshot of a Bluetooth device."""

    address: str
    name: str
    paired: bool
    connected: bool
    device_type: str    # "audio" | "input" | "phone" | "other"

    def icon_name(self) -> str:
        if self.device_type == "audio":
            return "audio-headphones-symbolic"
        if self.device_type == "input":
            return "input-keyboard-symbolic"
        if self.device_type == "phone":
            return "phone-symbolic"
        return "bluetooth-symbolic"


def _device_type_from_class(cod: int) -> str:
    """Map Class-of-Device major class bits to a type string."""
    major = (cod >> 8) & 0x1F
    if major == _COD_AUDIO:
        return "audio"
    if major == _COD_INPUT:
        return "input"
    if major == _COD_PHONE:
        return "phone"
    return "other"


class BluetoothManager:
    """
    Manages Bluetooth devices via org.bluez (dasbus, system bus).

    Usage::

        mgr = BluetoothManager(on_devices_changed=lambda devs: rebuild_list(devs))
        mgr.start()
    """

    def __init__(
        self,
        on_devices_changed: Callable[[list[BluetoothDevice]], None] | None = None,
    ) -> None:
        self._on_devices_changed = on_devices_changed
        self._bus = None
        self._adapter = None
        self._object_manager = None

    def start(self) -> None:
        try:
            self._connect()
        except Exception as exc:
            logger.warning("BluetoothManager: org.bluez unavailable: %s", exc)

    def is_available(self) -> bool:
        return self._adapter is not None

    def is_powered(self) -> bool:
        if self._adapter is None:
            return False
        try:
            return bool(self._adapter.Powered)
        except Exception:
            return False

    def set_powered(self, powered: bool) -> None:
        if self._adapter is None:
            return
        try:
            self._adapter.Powered = powered
        except Exception as exc:
            logger.warning("BluetoothManager: set_powered error: %s", exc)

    def start_discovery(self) -> None:
        if self._adapter is None:
            return
        try:
            self._adapter.StartDiscovery()
        except Exception as exc:
            logger.debug("BluetoothManager: StartDiscovery error: %s", exc)

    def stop_discovery(self) -> None:
        if self._adapter is None:
            return
        try:
            self._adapter.StopDiscovery()
        except Exception as exc:
            logger.debug("BluetoothManager: StopDiscovery error: %s", exc)

    def get_devices(self) -> list[BluetoothDevice]:
        if self._object_manager is None:
            return []
        try:
            return self._collect_devices()
        except Exception as exc:
            logger.debug("BluetoothManager: get_devices error: %s", exc)
            return []

    def connect_device(self, address: str) -> None:
        dev = self._get_device_proxy(address)
        if dev:
            try:
                dev.Connect()
            except Exception as exc:
                logger.warning("BluetoothManager: connect %s error: %s", address, exc)

    def disconnect_device(self, address: str) -> None:
        dev = self._get_device_proxy(address)
        if dev:
            try:
                dev.Disconnect()
            except Exception as exc:
                logger.warning("BluetoothManager: disconnect %s error: %s", address, exc)

    def pair_device(self, address: str) -> None:
        dev = self._get_device_proxy(address)
        if dev:
            try:
                dev.Pair()
            except Exception as exc:
                logger.warning("BluetoothManager: pair %s error: %s", address, exc)

    def remove_device(self, address: str) -> None:
        if self._adapter is None:
            return
        dev = self._get_device_proxy(address)
        if dev:
            try:
                path = self._address_to_path(address)
                self._adapter.RemoveDevice(path)
            except Exception as exc:
                logger.warning("BluetoothManager: remove %s error: %s", address, exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        from dasbus.connection import SystemMessageBus
        self._bus = SystemMessageBus()
        self._object_manager = self._bus.get_proxy(_BLUEZ_BUS, "/")
        try:
            self._adapter = self._bus.get_proxy(_BLUEZ_BUS, _ADAPTER_PATH)
            self._adapter.PropertiesChanged.connect(
                lambda *_: self._emit_devices()
            )
        except Exception:
            logger.debug("BluetoothManager: no adapter at %s", _ADAPTER_PATH)

    def _collect_devices(self) -> list[BluetoothDevice]:
        objects = self._object_manager.GetManagedObjects()
        devices: list[BluetoothDevice] = []
        for path, interfaces in objects.items():
            if _BLUEZ_DEVICE not in interfaces:
                continue
            props = interfaces[_BLUEZ_DEVICE]
            addr    = str(props.get("Address", ""))
            name    = str(props.get("Name", addr))
            paired  = bool(props.get("Paired", False))
            connected = bool(props.get("Connected", False))
            cod     = int(props.get("Class", 0))
            dev_type = _device_type_from_class(cod)
            devices.append(BluetoothDevice(
                address=addr,
                name=name,
                paired=paired,
                connected=connected,
                device_type=dev_type,
            ))
        devices.sort(key=lambda d: (-d.connected, -d.paired, d.name.lower()))
        return devices

    def _get_device_proxy(self, address: str):
        if self._bus is None:
            return None
        try:
            path = self._address_to_path(address)
            return self._bus.get_proxy(_BLUEZ_BUS, path)
        except Exception:
            return None

    @staticmethod
    def _address_to_path(address: str) -> str:
        """Convert "AA:BB:CC:DD:EE:FF" → "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"."""
        return _ADAPTER_PATH + "/dev_" + address.replace(":", "_")

    def _emit_devices(self) -> None:
        if self._on_devices_changed:
            devs = self.get_devices()
            try:
                from gi.repository import GLib
                GLib.idle_add(lambda: self._on_devices_changed(devs) or False)
            except ImportError:
                self._on_devices_changed(devs)
