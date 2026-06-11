"""MacUX install manifest — source → destination file mappings.

An ``InstallManifest`` lists every file that MacUX installs on the system.
The installer uses it both to place files and (later) to remove them cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InstallEntry:
    """A single source → destination file mapping."""

    source: Path   # relative to the project root
    dest: Path     # absolute path on the target system
    mode: int = 0o644  # octal file permission

    @property
    def dest_dir(self) -> Path:
        return self.dest.parent

    def is_executable(self) -> bool:
        return bool(self.mode & 0o111)


@dataclass
class InstallManifest:
    """All files to be installed (or removed) by the MacUX installer."""

    entries: list[InstallEntry] = field(default_factory=list)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def sources(self) -> list[Path]:
        return [e.source for e in self.entries]

    def dests(self) -> list[Path]:
        return [e.dest for e in self.entries]

    def dest_dirs(self) -> set[Path]:
        return {e.dest_dir for e in self.entries}

    # ── Integrity checks ──────────────────────────────────────────────────────

    def has_duplicate_dests(self) -> bool:
        """True if two entries share the same destination path."""
        dests = self.dests()
        return len(dests) != len(set(dests))

    def missing_sources(self, project_root: Path) -> list[Path]:
        """Return source paths that do not exist under *project_root*."""
        return [e.source for e in self.entries if not (project_root / e.source).exists()]

    # ── Filtering ─────────────────────────────────────────────────────────────

    def filter_by_dest_prefix(self, prefix: Path) -> InstallManifest:
        """Return a new manifest with only entries whose dest is under *prefix*."""
        return InstallManifest(
            [e for e in self.entries if _is_relative_to(e.dest, prefix)]
        )

    def filter_by_source_suffix(self, suffix: str) -> InstallManifest:
        """Return entries whose source path ends with *suffix*."""
        return InstallManifest(
            [e for e in self.entries if e.source.suffix == suffix]
        )

    def __len__(self) -> int:
        return len(self.entries)


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


# ── Canonical MacUX install manifest ──────────────────────────────────────────

_SHARE = Path("/usr/share")
_SYSTEMD_USER = Path("/usr/lib/systemd/user")
_DBUS_SERVICES = Path("/usr/share/dbus-1/services")
_GNOME_EXTENSIONS = Path("/usr/share/gnome-shell/extensions")

_COMPONENTS = [
    "dock",
    "finder",
    "launchpad",
    "menu-bar",
    "control-center",
    "notification-center",
    "mission-control",
    "spotlight",
]


def build_manifest() -> InstallManifest:
    """Return the canonical install manifest for MacUX 1.0.0."""
    entries: list[InstallEntry] = []

    # Desktop entries
    for comp in _COMPONENTS:
        entries.append(InstallEntry(
            source=Path(f"data/applications/macux-{comp}.desktop"),
            dest=_SHARE / "applications" / f"macux-{comp}.desktop",
            mode=0o644,
        ))

    # Systemd user services
    for comp in _COMPONENTS:
        entries.append(InstallEntry(
            source=Path(f"data/systemd/macux-{comp}.service"),
            dest=_SYSTEMD_USER / f"macux-{comp}.service",
            mode=0o644,
        ))

    # Spotlight indexer timer
    entries.append(InstallEntry(
        source=Path("installer/systemd/macux-spotlight-indexer.timer"),
        dest=_SYSTEMD_USER / "macux-spotlight-indexer.timer",
        mode=0o644,
    ))

    # Orchestrator daemon service
    entries.append(InstallEntry(
        source=Path("installer/systemd/macux.service"),
        dest=_SYSTEMD_USER / "macux.service",
        mode=0o644,
    ))

    # GSettings schemas (compiled separately)
    for schema_src, schema_file in [
        (
            "gnome-shell/extensions/macux-mission-control@macux/schemas/"
            "org.gnome.shell.extensions.macux-mission-control.gschema.xml",
            "org.gnome.shell.extensions.macux-mission-control.gschema.xml",
        ),
        (
            "gnome-extensions/macux-shell@macux.com/schemas/"
            "org.gnome.shell.extensions.macux.gschema.xml",
            "org.gnome.shell.extensions.macux.gschema.xml",
        ),
    ]:
        entries.append(InstallEntry(
            source=Path(schema_src),
            dest=_SHARE / "glib-2.0" / "schemas" / schema_file,
            mode=0o644,
        ))

    # Default config
    entries.append(InstallEntry(
        source=Path("config/config.toml.default"),
        dest=_SHARE / "macux" / "config.toml.default",
        mode=0o644,
    ))

    # GNOME Shell extensions
    entries.append(InstallEntry(
        source=Path("gnome-shell/extensions/macux-mission-control@macux"),
        dest=_GNOME_EXTENSIONS / "macux-mission-control@macux",
        mode=0o755,
    ))
    entries.append(InstallEntry(
        source=Path("gnome-extensions/macux-shell@macux.com"),
        dest=_GNOME_EXTENSIONS / "macux-shell@macux.com",
        mode=0o755,
    ))

    return InstallManifest(entries)
