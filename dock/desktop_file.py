"""MacUX Dock — .desktop file parser and XDG app database.

Parses XDG .desktop files from:
  - /usr/share/applications/
  - /usr/local/share/applications/
  - ~/.local/share/applications/

Spec: https://specifications.freedesktop.org/desktop-entry-spec/latest/
"""

from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# XDG application search paths (later entries override earlier)
_APP_DIRS: list[Path] = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("~/.local/share/applications").expanduser(),
]


@dataclass
class AppInfo:
    """Parsed representation of a single .desktop file."""

    desktop_id: str          # e.g. "org.gnome.Nautilus.desktop"
    name: str                # localised display name
    exec: str                # exec command (may contain %f, %u, etc.)
    icon: str                # icon name or absolute path
    categories: list[str]    # e.g. ["Utility", "GTK"]
    startup_wm_class: str    # WM_CLASS for running-app matching (may be "")
    nodisplay: bool          # True if hidden from app launchers
    path: str                # absolute path of the .desktop file
    comment: str = ""        # short description

    @property
    def exec_base(self) -> str:
        """Executable name without arguments or field codes."""
        parts = self.exec.split()
        if not parts:
            return ""
        base = parts[0]
        # Strip env-var prefixes like "env FOO=bar /usr/bin/app"
        while base in ("env", "sudo", "flatpak", "snap"):
            parts = parts[1:]
            if not parts:
                return ""
            base = parts[0]
        # Strip path prefix
        return Path(base).name

    def launch_command(self) -> list[str]:
        """Return a shell-safe command list with %u/%f field codes removed."""
        raw = self.exec
        # Strip field codes
        for code in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N",
                     "%i", "%c", "%k", "%v", "%m"):
            raw = raw.replace(code, "")
        return raw.split()


class DesktopFileParser:
    """
    Scans XDG application directories and builds an AppInfo registry.

    Usage::

        parser = DesktopFileParser()
        apps = parser.load_all()          # -> dict[desktop_id, AppInfo]
        app  = parser.find("firefox")     # by name, id, or exec base
    """

    def __init__(self, search_dirs: list[Path] | None = None) -> None:
        self._dirs = search_dirs if search_dirs is not None else _APP_DIRS
        self._registry: dict[str, AppInfo] | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load_all(self) -> dict[str, AppInfo]:
        """
        Scan all app dirs and return a dict keyed by desktop_id.
        Later entries (user overrides) win over earlier (system) entries.
        """
        registry: dict[str, AppInfo] = {}
        for app_dir in self._dirs:
            if not app_dir.is_dir():
                continue
            for desktop_path in sorted(app_dir.glob("*.desktop")):
                info = self._parse_file(desktop_path)
                if info is not None:
                    registry[info.desktop_id] = info

        self._registry = registry
        logger.debug("DesktopFileParser: loaded %d apps", len(registry))
        return registry

    def find(self, query: str) -> AppInfo | None:
        """
        Fuzzy lookup by:
          1. Exact desktop_id  ("org.gnome.Nautilus.desktop")
          2. Name prefix (case-insensitive)
          3. exec_base prefix
        Returns the first match or None.
        """
        if self._registry is None:
            self.load_all()
        assert self._registry is not None

        q = query.lower().rstrip(".desktop")

        # 1. Exact match
        if query in self._registry:
            return self._registry[query]

        # 2. Name or exec_base prefix match
        candidates = []
        for info in self._registry.values():
            if (info.name.lower().startswith(q)
                    or info.exec_base.lower() == q
                    or info.desktop_id.lower().startswith(q)):
                candidates.append(info)

        if not candidates:
            return None
        # Prefer shorter names (more specific match)
        return min(candidates, key=lambda a: len(a.name))

    def get(self, desktop_id: str) -> AppInfo | None:
        """Return AppInfo by exact desktop_id, loading registry if needed."""
        if self._registry is None:
            self.load_all()
        return self._registry.get(desktop_id)  # type: ignore[union-attr]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_file(self, path: Path) -> AppInfo | None:
        """Parse a single .desktop file. Returns None on failure or non-Application type."""
        cp = configparser.RawConfigParser(strict=False)
        try:
            cp.read(str(path), encoding="utf-8")
        except Exception as exc:
            logger.debug("Cannot read %s: %s", path, exc)
            return None

        section = "Desktop Entry"
        if not cp.has_section(section):
            return None

        entry_type = cp.get(section, "Type", fallback="")
        if entry_type != "Application":
            return None

        name = self._localised(cp, section, "Name")
        if not name:
            return None

        exec_str = cp.get(section, "Exec", fallback="")
        icon = cp.get(section, "Icon", fallback="application-x-executable")
        raw_cats = cp.get(section, "Categories", fallback="")
        categories = [c for c in raw_cats.split(";") if c]
        nodisplay = cp.getboolean(section, "NoDisplay", fallback=False)
        startup_wm_class = cp.get(section, "StartupWMClass", fallback="")
        comment = self._localised(cp, section, "Comment")

        return AppInfo(
            desktop_id=path.name,
            name=name,
            exec=exec_str,
            icon=icon,
            categories=categories,
            startup_wm_class=startup_wm_class,
            nodisplay=nodisplay,
            path=str(path),
            comment=comment,
        )

    @staticmethod
    def _localised(cp: configparser.RawConfigParser, section: str, key: str) -> str:
        """
        Return the best locale match for a key.
        Tries LANG, then LANGUAGE, then falls back to the bare key.
        """
        lang = os.environ.get("LANG", "")
        if lang:
            locale = lang.split(".")[0]  # e.g. "en_US"
            short = locale.split("_")[0]   # e.g. "en"
            for candidate in (f"{key}[{locale}]", f"{key}[{short}]"):
                if cp.has_option(section, candidate):
                    return cp.get(section, candidate)
        return cp.get(section, key, fallback="")
