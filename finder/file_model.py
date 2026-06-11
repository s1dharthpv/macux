"""MacUX Finder — GTK-free file model.

All types here are pure Python dataclasses testable without a display.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SortKey(Enum):
    NAME = "name"
    SIZE = "size"
    MODIFIED = "modified"
    KIND = "kind"


class ViewMode(Enum):
    ICON = "icon"
    LIST = "list"
    COLUMN = "column"


@dataclass
class FileItem:
    """Snapshot of a single filesystem entry."""

    path: Path
    name: str
    size: int        # bytes; 0 for directories
    mtime: float     # Unix timestamp
    mime_type: str   # e.g. "text/plain", "inode/directory"
    is_dir: bool
    is_symlink: bool
    is_hidden: bool  # name starts with "."
    tags: list[str] = field(default_factory=list)

    @property
    def extension(self) -> str:
        if self.is_dir:
            return ""
        return self.path.suffix.lstrip(".").lower()

    @property
    def display_size(self) -> str:
        if self.is_dir:
            return "—"
        if self.size < 1_024:
            return f"{self.size} B"
        if self.size < 1_024 ** 2:
            return f"{self.size / 1_024:.1f} KB"
        if self.size < 1_024 ** 3:
            return f"{self.size / 1_024 ** 2:.1f} MB"
        return f"{self.size / 1_024 ** 3:.1f} GB"

    @property
    def display_mtime(self) -> str:
        return time.strftime("%b %-d, %Y", time.localtime(self.mtime))

    def icon_name(self) -> str:
        if self.is_dir:
            return "folder-symbolic"
        mime = self.mime_type
        if mime.startswith("image/"):
            return "image-x-generic-symbolic"
        if mime.startswith("video/"):
            return "video-x-generic-symbolic"
        if mime.startswith("audio/"):
            return "audio-x-generic-symbolic"
        if mime == "application/pdf":
            return "x-office-document-symbolic"
        if mime.startswith("text/"):
            return "text-x-generic-symbolic"
        if mime in (
            "application/zip", "application/x-tar", "application/x-bzip2",
            "application/x-gzip", "application/x-xz",
            "application/x-7z-compressed", "application/x-rar",
        ):
            return "package-x-generic-symbolic"
        return "text-x-generic-symbolic"


# ── MIME type lookup table ─────────────────────────────────────────────────────

_MIME_MAP: dict[str, str] = {
    # images
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
    "heic": "image/heic", "bmp": "image/bmp", "tiff": "image/tiff",
    "ico": "image/x-icon",
    # video
    "mp4": "video/mp4", "mkv": "video/x-matroska", "avi": "video/x-msvideo",
    "mov": "video/quicktime", "webm": "video/webm", "flv": "video/x-flv",
    # audio
    "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg",
    "wav": "audio/wav", "aac": "audio/aac", "m4a": "audio/mp4",
    "opus": "audio/opus",
    # documents
    "pdf": "application/pdf",
    "txt": "text/plain", "md": "text/markdown", "rst": "text/x-rst",
    "html": "text/html", "htm": "text/html",
    "css": "text/css", "js": "text/javascript",
    "py": "text/x-python", "sh": "text/x-shellscript",
    "json": "application/json", "xml": "text/xml",
    "yaml": "text/yaml", "yml": "text/yaml",
    "csv": "text/csv", "tsv": "text/tab-separated-values",
    "c": "text/x-c", "h": "text/x-c", "cpp": "text/x-c++",
    "rs": "text/x-rust", "go": "text/x-go",
    # archives
    "zip": "application/zip", "tar": "application/x-tar",
    "gz": "application/x-gzip", "bz2": "application/x-bzip2",
    "xz": "application/x-xz", "7z": "application/x-7z-compressed",
    "rar": "application/x-rar",
}


def _guess_mime(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "inode/directory"
    ext = path.suffix.lstrip(".").lower()
    return _MIME_MAP.get(ext, "application/octet-stream")


def make_file_item(path: Path) -> FileItem:
    """Build a FileItem by stat-ing *path*."""
    is_symlink = path.is_symlink()
    is_dir = path.is_dir()

    try:
        st = path.lstat()
        size = st.st_size if not is_dir else 0
        mtime = st.st_mtime
    except OSError:
        size = 0
        mtime = 0.0

    return FileItem(
        path=path,
        name=path.name,
        size=size,
        mtime=mtime,
        mime_type=_guess_mime(path, is_dir),
        is_dir=is_dir,
        is_symlink=is_symlink,
        is_hidden=path.name.startswith("."),
    )


# ── DirectoryListing ───────────────────────────────────────────────────────────

@dataclass
class DirectoryListing:
    """Sorted, optionally filtered snapshot of a directory."""

    directory: Path
    items: list[FileItem]

    @classmethod
    def load(
        cls,
        directory: Path,
        show_hidden: bool = False,
        sort_key: SortKey = SortKey.NAME,
        sort_reverse: bool = False,
    ) -> DirectoryListing:
        """Read *directory* and return a sorted listing.

        Returns an empty listing on ``OSError`` (permission denied, not found).
        """
        try:
            entries = list(directory.iterdir())
        except OSError:
            return cls(directory=directory, items=[])

        items = [make_file_item(p) for p in entries]

        if not show_hidden:
            items = [i for i in items if not i.is_hidden]

        return cls(
            directory=directory,
            items=sort_items(items, sort_key, sort_reverse),
        )

    def filter_by_name(self, query: str) -> list[FileItem]:
        """Items whose name contains *query* (case-insensitive)."""
        q = query.lower()
        return [i for i in self.items if q in i.name.lower()]

    @property
    def dirs(self) -> list[FileItem]:
        return [i for i in self.items if i.is_dir]

    @property
    def files(self) -> list[FileItem]:
        return [i for i in self.items if not i.is_dir]

    def __len__(self) -> int:
        return len(self.items)


def sort_items(
    items: list[FileItem],
    sort_key: SortKey = SortKey.NAME,
    reverse: bool = False,
) -> list[FileItem]:
    """Sort *items*: directories always before files, then by *sort_key*."""
    dirs = [i for i in items if i.is_dir]
    files = [i for i in items if not i.is_dir]

    key_fns = {
        SortKey.NAME: lambda i: i.name.lower(),
        SortKey.SIZE: lambda i: i.size,
        SortKey.MODIFIED: lambda i: i.mtime,
        SortKey.KIND: lambda i: i.mime_type,
    }
    key_fn = key_fns[sort_key]

    dirs.sort(key=key_fn, reverse=reverse)
    files.sort(key=key_fn, reverse=reverse)
    return dirs + files
