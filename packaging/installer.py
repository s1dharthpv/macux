"""MacUX programmatic installer with dry-run support."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from packaging.manifest import InstallManifest
from packaging.schema_compiler import compile_schemas, find_compile_tool

_log = logging.getLogger(__name__)


class InstallError(Exception):
    """Raised when a required install step fails."""


@dataclass
class InstallResult:
    installed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    @property
    def installed_count(self) -> int:
        return len(self.installed)


def install_manifest(
    manifest: InstallManifest,
    project_root: Path,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> InstallResult:
    """Install files described by *manifest*.

    In dry-run mode no files are written; *result.installed* lists what
    *would* be installed.
    """
    result = InstallResult()

    for entry in manifest.entries:
        src = project_root / entry.source
        dest = entry.dest

        if on_progress:
            on_progress(f"{src} → {dest}")

        if not src.exists():
            msg = f"Source not found: {src}"
            _log.warning(msg)
            result.errors.append(msg)
            continue

        if dry_run:
            result.installed.append(dest)
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            os.chmod(dest, entry.mode)
            result.installed.append(dest)
            _log.debug("Installed %s", dest)
        except OSError as exc:
            msg = f"Failed to install {src} → {dest}: {exc}"
            _log.error(msg)
            result.errors.append(msg)

    return result


def uninstall_manifest(
    manifest: InstallManifest,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> InstallResult:
    """Remove all files listed in *manifest*."""
    result = InstallResult()

    for entry in manifest.entries:
        dest = entry.dest

        if on_progress:
            on_progress(str(dest))

        if not dest.exists():
            result.skipped.append(dest)
            continue

        if dry_run:
            result.installed.append(dest)  # "would remove"
            continue

        try:
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
            result.installed.append(dest)
            _try_rmdir(dest.parent)
        except OSError as exc:
            result.errors.append(str(exc))

    return result


def _try_rmdir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def check_dependencies() -> dict[str, bool]:
    """Return a dict of tool → is_available for required tools."""
    return {
        "glib-compile-schemas": find_compile_tool() is not None,
        "gnome-shell": shutil.which("gnome-shell") is not None,
        "systemctl": shutil.which("systemctl") is not None,
        "python3": shutil.which("python3") is not None,
        "glib-compile-resources": shutil.which("glib-compile-resources") is not None,
    }


def reload_systemd_user() -> bool:
    """Run ``systemctl --user daemon-reload``."""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def enable_systemd_units(unit_names: list[str]) -> dict[str, bool]:
    """Enable a list of systemd user units.  Returns unit → success map."""
    results: dict[str, bool] = {}
    for unit in unit_names:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "enable", unit],
                capture_output=True,
                timeout=15,
            )
            results[unit] = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            results[unit] = False
    return results
