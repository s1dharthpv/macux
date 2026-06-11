"""MacUX Finder — file operations (copy, move, rename, delete, trash).

All functions raise FileOpsError on failure.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]  # done, total, current_name


class FileOpsError(Exception):
    """Raised when a file operation cannot be completed."""


def copy_file(
    src: Path,
    dest_dir: Path,
    on_progress: ProgressCallback | None = None,
    overwrite: bool = False,
) -> Path:
    """Copy *src* into *dest_dir*.

    Returns the destination path.  Raises :exc:`FileOpsError` if the source
    does not exist, the destination is not a directory, or the target already
    exists and *overwrite* is False.
    """
    if not src.exists() and not src.is_symlink():
        raise FileOpsError(f"Source does not exist: {src}")
    if not dest_dir.is_dir():
        raise FileOpsError(f"Destination is not a directory: {dest_dir}")

    dest = dest_dir / src.name
    if dest.exists() and not overwrite:
        raise FileOpsError(f"Destination already exists: {dest}")

    try:
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=overwrite)
        else:
            shutil.copy2(src, dest)
    except OSError as exc:
        raise FileOpsError(str(exc)) from exc

    if on_progress:
        on_progress(1, 1, src.name)
    return dest


def move_file(
    src: Path,
    dest_dir: Path,
    overwrite: bool = False,
) -> Path:
    """Move *src* into *dest_dir*.

    Returns the destination path.
    """
    if not src.exists() and not src.is_symlink():
        raise FileOpsError(f"Source does not exist: {src}")
    if not dest_dir.is_dir():
        raise FileOpsError(f"Destination is not a directory: {dest_dir}")

    dest = dest_dir / src.name
    if dest.exists() and not overwrite:
        raise FileOpsError(f"Destination already exists: {dest}")

    try:
        shutil.move(str(src), str(dest))
    except (OSError, shutil.Error) as exc:
        raise FileOpsError(str(exc)) from exc

    return dest


def rename_file(src: Path, new_name: str) -> Path:
    """Rename *src* to *new_name* in the same directory.

    Returns the new path.  Raises :exc:`FileOpsError` for invalid names or
    name conflicts.
    """
    if not src.exists() and not src.is_symlink():
        raise FileOpsError(f"Source does not exist: {src}")
    if not new_name or "/" in new_name or new_name in (".", ".."):
        raise FileOpsError(f"Invalid name: {new_name!r}")

    dest = src.parent / new_name
    if dest.exists():
        raise FileOpsError(f"A file named {new_name!r} already exists")

    try:
        src.rename(dest)
    except OSError as exc:
        raise FileOpsError(str(exc)) from exc

    return dest


def delete_file(path: Path) -> None:
    """Permanently delete *path* (file, symlink, or directory tree)."""
    if not path.exists() and not path.is_symlink():
        raise FileOpsError(f"Path does not exist: {path}")

    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        raise FileOpsError(str(exc)) from exc


def trash_file(path: Path) -> None:
    """Move *path* to the user trash via GIO.

    Falls back to permanent deletion if GIO is unavailable or trash fails.
    """
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        f = Gio.File.new_for_path(str(path))
        f.trash(None)
    except Exception as exc:
        _log.warning("GIO trash failed (%s), falling back to delete", exc)
        delete_file(path)


def create_folder(parent: Path, name: str) -> Path:
    """Create a new subdirectory named *name* inside *parent*.

    Returns the new directory path.
    """
    if not parent.is_dir():
        raise FileOpsError(f"Parent is not a directory: {parent}")
    if not name or "/" in name or name in (".", ".."):
        raise FileOpsError(f"Invalid folder name: {name!r}")

    dest = parent / name
    if dest.exists():
        raise FileOpsError(f"Already exists: {dest}")

    try:
        dest.mkdir(parents=False)
    except OSError as exc:
        raise FileOpsError(str(exc)) from exc

    return dest
