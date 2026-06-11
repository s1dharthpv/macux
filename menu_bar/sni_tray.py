# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""MacUX Menu Bar — SNI (StatusNotifierItem) system tray discovery.

SniItem is a pure dataclass representing one tray item.
SniWatcher monitors the KDE StatusNotifierWatcher DBus service and
tracks registered/unregistered items using the session bus.

No GTK — pure model/discovery layer.
"""

import dataclasses
import logging
from typing import Any, Callable

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

logger = logging.getLogger(__name__)

_SNI_WATCHER_BUS  = "org.kde.StatusNotifierWatcher"
_SNI_WATCHER_PATH = "/StatusNotifierWatcher"
_SNI_ITEM_PATH    = "/StatusNotifierItem"

_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_SNI_IFACE   = "org.kde.StatusNotifierItem"


@dataclasses.dataclass
class SniItem:
    """Snapshot of one StatusNotifierItem tray entry."""

    service: str        # e.g. "org.kde.StatusNotifierItem-1234-1"
    object_path: str    # e.g. "/StatusNotifierItem"
    id: str             # App id (from SNI property Id)
    title: str          # Human-readable title
    icon_name: str      # Symbolic icon name or empty string
    icon_pixmap: bytes  # Raw PNG bytes or empty bytes
    tooltip: str
    status: str         # "Active", "Passive", "NeedsAttention"
    category: str       # "ApplicationStatus", "SystemServices", etc.

    @property
    def is_active(self) -> bool:
        return self.status != "Passive"


class SniWatcher:
    """Monitors the SNI watcher DBus service and tracks registered items.

    Usage::

        watcher = SniWatcher(
            on_item_added=lambda item: print("added", item.title),
            on_item_removed=lambda service: print("removed", service),
        )
        if watcher.start():
            # items available via watcher.get_items()
            ...
        watcher.stop()
    """

    def __init__(
        self,
        on_item_added: Callable[[SniItem], None] | None = None,
        on_item_removed: Callable[[str], None] | None = None,
    ) -> None:
        self._on_item_added   = on_item_added
        self._on_item_removed = on_item_removed
        self._items: dict[str, SniItem] = {}  # keyed by service name
        self._subscription_ids: list[int] = []
        self._bus: Gio.DBusConnection | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Connect to org.kde.StatusNotifierWatcher.

        Returns False if the watcher service is not available on the session bus.
        """
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as exc:
            logger.warning("SniWatcher: cannot connect to session bus: %s", exc)
            return False

        # Check that the watcher is actually present
        if not self._watcher_available():
            logger.debug("SniWatcher: %s not available", _SNI_WATCHER_BUS)
            return False

        # Seed with items that are already registered
        self._load_existing_items()

        # Subscribe to new registrations and removals
        self._subscribe_signals()
        return True

    def stop(self) -> None:
        """Disconnect from all signals."""
        if self._bus is not None:
            for sub_id in self._subscription_ids:
                try:
                    self._bus.signal_unsubscribe(sub_id)
                except Exception:
                    pass
        self._subscription_ids.clear()
        self._bus = None

    def get_items(self) -> list[SniItem]:
        """Return a copy of currently tracked items, sorted by title."""
        return sorted(self._items.values(), key=lambda item: item.title.lower())

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _watcher_available(self) -> bool:
        """Return True if the StatusNotifierWatcher name is owned on the bus."""
        assert self._bus is not None
        try:
            result = self._bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", (_SNI_WATCHER_BUS,)),
                GLib.VariantType("(b)"),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
            return bool(result.unpack()[0])
        except GLib.Error as exc:
            logger.debug("SniWatcher: NameHasOwner failed: %s", exc)
            return False

    def _load_existing_items(self) -> None:
        """Read RegisteredStatusNotifierItems from the watcher and seed _items."""
        assert self._bus is not None
        try:
            result = self._bus.call_sync(
                _SNI_WATCHER_BUS,
                _SNI_WATCHER_PATH,
                _PROPS_IFACE,
                "Get",
                GLib.Variant("(ss)", (_SNI_WATCHER_BUS, "RegisteredStatusNotifierItems")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
            items_variant = result.unpack()[0]
            registered: list[str] = list(items_variant) if items_variant else []
        except GLib.Error as exc:
            logger.debug("SniWatcher: could not read existing items: %s", exc)
            return

        for service in registered:
            item = self._fetch_item(service)
            if item is not None:
                self._items[service] = item

    def _subscribe_signals(self) -> None:
        """Subscribe to ItemRegistered and ItemUnregistered signals."""
        assert self._bus is not None

        registered_id = self._bus.signal_subscribe(
            _SNI_WATCHER_BUS,
            _SNI_WATCHER_BUS,
            "StatusNotifierItemRegistered",
            _SNI_WATCHER_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_registered,
            None,
        )
        unregistered_id = self._bus.signal_subscribe(
            _SNI_WATCHER_BUS,
            _SNI_WATCHER_BUS,
            "StatusNotifierItemUnregistered",
            _SNI_WATCHER_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_unregistered,
            None,
        )
        self._subscription_ids.extend([registered_id, unregistered_id])

    def _on_registered(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        signal_name: str,
        parameters: GLib.Variant,
        user_data: Any,
    ) -> None:
        service = parameters.unpack()[0]
        item = self._fetch_item(service)
        if item is not None:
            self._items[service] = item
            if self._on_item_added is not None:
                try:
                    self._on_item_added(item)
                except Exception as exc:
                    logger.debug("SniWatcher: on_item_added raised: %s", exc)

    def _on_unregistered(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        signal_name: str,
        parameters: GLib.Variant,
        user_data: Any,
    ) -> None:
        service = parameters.unpack()[0]
        self._items.pop(service, None)
        if self._on_item_removed is not None:
            try:
                self._on_item_removed(service)
            except Exception as exc:
                logger.debug("SniWatcher: on_item_removed raised: %s", exc)

    def _fetch_item(self, service: str) -> SniItem | None:
        """Fetch SNI properties from *service* and return an SniItem, or None on error."""
        assert self._bus is not None
        try:
            result = self._bus.call_sync(
                service,
                _SNI_ITEM_PATH,
                _PROPS_IFACE,
                "GetAll",
                GLib.Variant("(s)", (_SNI_IFACE,)),
                GLib.VariantType("(a{sv})"),
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
        except GLib.Error as exc:
            # Item may have vanished before we could read it — not an error
            logger.debug("SniWatcher: could not fetch props for %s: %s", service, exc)
            return None

        props: dict[str, Any] = {}
        raw_dict = result.unpack()[0]
        for key, val in raw_dict.items():
            props[key] = val

        # Extract icon pixmap (first pixmap entry, raw bytes, or empty)
        icon_pixmap = self._extract_pixmap(props.get("IconPixmap"))

        return SniItem(
            service=service,
            object_path=_SNI_ITEM_PATH,
            id=str(props.get("Id", "")),
            title=str(props.get("Title", service)),
            icon_name=str(props.get("IconName", "")),
            icon_pixmap=icon_pixmap,
            tooltip=self._extract_tooltip(props.get("ToolTip")),
            status=str(props.get("Status", "Active")),
            category=str(props.get("Category", "ApplicationStatus")),
        )

    @staticmethod
    def _extract_pixmap(pixmap_value: Any) -> bytes:
        """Extract raw bytes from the SNI IconPixmap array-of-structs, or b''."""
        if not pixmap_value:
            return b""
        try:
            # IconPixmap is a(iiay): array of (width, height, data)
            entries = list(pixmap_value)
            if entries:
                # Take the first (largest isn't guaranteed, but first is fine for display)
                _w, _h, data = entries[0]
                return bytes(data)
        except Exception:
            pass
        return b""

    @staticmethod
    def _extract_tooltip(tooltip_value: Any) -> str:
        """Extract a plain string from the SNI ToolTip struct (sa(iiay)ss), or ''."""
        if not tooltip_value:
            return ""
        try:
            # ToolTip is (sa(iiay)ss): (icon_name, icon_data, title, description)
            parts = tuple(tooltip_value)
            # title is index 2, description is index 3
            title = str(parts[2]) if len(parts) > 2 else ""
            description = str(parts[3]) if len(parts) > 3 else ""
            if description:
                return f"{title}: {description}" if title else description
            return title
        except Exception:
            return ""
