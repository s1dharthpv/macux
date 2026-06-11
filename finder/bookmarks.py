"""MacUX Finder — GTK bookmark manager.

Reads and writes the standard GTK bookmarks file
(``~/.config/gtk-3.0/bookmarks``), which stores one URI per line with an
optional display label after a space.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

_log = logging.getLogger(__name__)

_DEFAULT_BOOKMARKS_FILE = Path.home() / ".config" / "gtk-3.0" / "bookmarks"


class Bookmark(NamedTuple):
    uri: str
    label: str  # empty string means use the URI-derived name

    @property
    def path(self) -> Path | None:
        """Return a ``Path`` if the URI is a local ``file://`` URL, else None."""
        if self.uri.startswith("file://"):
            return Path(self.uri[7:])
        return None

    @property
    def display_name(self) -> str:
        if self.label:
            return self.label
        if self.uri.startswith("file://"):
            p = Path(self.uri[7:])
            return p.name or self.uri
        return self.uri


class BookmarkManager:
    """Read and write the GTK bookmarks file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_BOOKMARKS_FILE
        self._bookmarks: list[Bookmark] = []
        self._load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def all(self) -> list[Bookmark]:
        return list(self._bookmarks)

    def add(self, path: Path, label: str = "") -> None:
        """Add *path* as a bookmark.  No-op if already present."""
        uri = _path_to_uri(path)
        if any(b.uri == uri for b in self._bookmarks):
            return
        self._bookmarks.append(Bookmark(uri=uri, label=label))
        self._save()

    def remove(self, path: Path) -> bool:
        """Remove the bookmark for *path*.  Returns True if it existed."""
        uri = _path_to_uri(path)
        before = len(self._bookmarks)
        self._bookmarks = [b for b in self._bookmarks if b.uri != uri]
        if len(self._bookmarks) < before:
            self._save()
            return True
        return False

    def contains(self, path: Path) -> bool:
        return any(b.uri == _path_to_uri(path) for b in self._bookmarks)

    def rename(self, path: Path, new_label: str) -> bool:
        """Change the display label for *path*.  Returns True if found."""
        uri = _path_to_uri(path)
        for i, b in enumerate(self._bookmarks):
            if b.uri == uri:
                self._bookmarks[i] = Bookmark(uri=uri, label=new_label)
                self._save()
                return True
        return False

    # ── Private ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        self._bookmarks = []
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            _log.warning("Cannot read bookmarks: %s", exc)
            return

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            uri = parts[0]
            label = parts[1] if len(parts) > 1 else ""
            self._bookmarks.append(Bookmark(uri=uri, label=label))

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            lines: list[str] = []
            for b in self._bookmarks:
                lines.append(f"{b.uri} {b.label}".rstrip())
            self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            _log.error("Cannot write bookmarks: %s", exc)


def _path_to_uri(path: Path) -> str:
    return f"file://{path}"
