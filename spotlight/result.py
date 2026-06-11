"""MacUX Spotlight — SearchResult dataclass and category constants."""

from __future__ import annotations

from dataclasses import dataclass, field

# Search categories (also used as DBus filter strings)
CAT_APPS       = "apps"
CAT_FILES      = "files"
CAT_FOLDERS    = "folders"
CAT_CALCULATOR = "calculator"
CAT_WEB        = "web"

ALL_CATEGORIES = [CAT_APPS, CAT_FILES, CAT_FOLDERS, CAT_CALCULATOR, CAT_WEB]

# Action types (what happens on Enter / double-click)
ACTION_LAUNCH = "launch"   # exec the .desktop file
ACTION_OPEN   = "open"     # open the file with xdg-open
ACTION_COPY   = "copy"     # copy result text to clipboard
ACTION_URL    = "url"      # open URL in browser


@dataclass
class SearchResult:
    """
    A single Spotlight search result.

    Attributes:
        category: One of CAT_* constants.
        name:     Primary display text (large, bold).
        path:     Filesystem path, URI, or "" for calculator/web results.
        icon:     Icon theme name or absolute file path.
        score:    Relevance score 0.0–1.0 (higher = better).
        subtitle: Secondary text (directory, file type, description, …).
        action:   What to do when the user activates this result.
        metadata: Extra payload (e.g. {"result": "42"} for calculator).
    """

    category: str
    name: str
    path: str = ""
    icon: str = "application-x-executable"
    score: float = 0.5
    subtitle: str = ""
    action: str = ACTION_OPEN
    metadata: dict = field(default_factory=dict)

    def to_dbus_dict(self) -> dict:
        """Serialise to the aa{sv} DBus format expected by the Search method."""
        return {
            "type":     self.category,
            "name":     self.name,
            "path":     self.path,
            "icon":     self.icon,
            "score":    float(self.score),
            "subtitle": self.subtitle,
            "action":   self.action,
        }

    @classmethod
    def from_dbus_dict(cls, d: dict) -> "SearchResult":
        return cls(
            category=d.get("type", CAT_FILES),
            name=d.get("name", ""),
            path=d.get("path", ""),
            icon=d.get("icon", ""),
            score=float(d.get("score", 0.5)),
            subtitle=d.get("subtitle", ""),
            action=d.get("action", ACTION_OPEN),
        )
