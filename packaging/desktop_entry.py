"""Desktop entry (.desktop file) parser and validator.

Implements a subset of the XDG Desktop Entry specification
(https://specifications.freedesktop.org/desktop-entry-spec/latest/).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_FIELDS: frozenset[str] = frozenset({"Type", "Name", "Exec"})


@dataclass
class DesktopEntry:
    """Parsed representation of a ``.desktop`` file."""

    path: Path | None
    entries: dict[str, str] = field(default_factory=dict)

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.entries.get("Name", "")

    @property
    def exec_cmd(self) -> str:
        return self.entries.get("Exec", "")

    @property
    def type_(self) -> str:
        return self.entries.get("Type", "")

    @property
    def icon(self) -> str:
        return self.entries.get("Icon", "")

    @property
    def comment(self) -> str:
        return self.entries.get("Comment", "")

    @property
    def categories(self) -> list[str]:
        raw = self.entries.get("Categories", "")
        return [c for c in raw.split(";") if c]

    @property
    def no_display(self) -> bool:
        return self.entries.get("NoDisplay", "false").lower() == "true"

    @property
    def startup_notify(self) -> bool:
        return self.entries.get("StartupNotify", "false").lower() == "true"

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of validation errors; empty list means valid."""
        errors: list[str] = []
        for field_name in sorted(REQUIRED_FIELDS):
            if not self.entries.get(field_name):
                errors.append(f"Missing required field: {field_name}")
        return errors

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    # ── Parsing ───────────────────────────────────────────────────────────────

    @classmethod
    def parse(cls, text: str, path: Path | None = None) -> DesktopEntry:
        """Parse a .desktop file from *text*.

        Only the ``[Desktop Entry]`` section is read.  Comment lines (#)
        and blank lines are ignored.
        """
        entries: dict[str, str] = {}
        in_section = False

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line == "[Desktop Entry]":
                in_section = True
                continue
            if line.startswith("["):
                if in_section:
                    break  # another section starts — stop
                continue
            if in_section and "=" in line:
                key, _, value = line.partition("=")
                entries[key.strip()] = value.strip()

        return cls(path=path, entries=entries)

    @classmethod
    def load(cls, path: Path) -> DesktopEntry:
        """Read *path* from disk and parse it."""
        return cls.parse(path.read_text(encoding="utf-8"), path=path)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_string(self) -> str:
        """Render the entry back to .desktop file format."""
        lines = ["[Desktop Entry]"]
        for key, value in self.entries.items():
            lines.append(f"{key}={value}")
        lines.append("")
        return "\n".join(lines)
