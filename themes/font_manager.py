"""
MacUX Font Manager — detects, loads, and configures the UI font.

Priority chain:
  1. SF Pro Display / SF Pro Text  (if user has installed Apple fonts)
  2. Inter                         (if installed via apt/user)
  3. Cantarell                     (GNOME default — always available)
  4. sans-serif                    (system fallback)

Also generates a fontconfig XML override file that makes the chosen
font the default sans-serif for all MacUX applications.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_FONTCONFIG_DIR = Path("~/.config/macux/fonts").expanduser()
_FONTCONFIG_PATH = _FONTCONFIG_DIR / "macux-fonts.conf"


@dataclass
class FontConfig:
    """Resolved font configuration for the MacUX design system."""
    ui_family: str         # primary UI font (display text, labels)
    ui_monospace: str      # monospace font (code, paths)
    ui_size: int           # base size in points
    ui_size_sm: int        # small (captions, labels)
    ui_size_lg: int        # large (titles)
    ui_size_xl: int        # extra large (hero text)
    weight_regular: int    # 400
    weight_medium: int     # 500
    weight_semibold: int   # 600
    weight_bold: int       # 700
    line_height: float     # 1.3–1.5
    letter_spacing_tight: float   # em units
    letter_spacing_normal: float
    letter_spacing_wide: float


def _fc_list_families() -> set[str]:
    """Return the set of font family names installed on this system."""
    try:
        result = subprocess.run(
            ["fc-list", "--format=%{family[0]}\n"],
            capture_output=True, text=True, timeout=10,
        )
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("fc-list not available; using fallback font detection")
        return set()


class FontManager:
    """
    Detects available fonts and resolves the MacUX font configuration.
    Generates a fontconfig override file for consistent rendering.
    """

    # Ordered preference list of UI fonts
    _UI_FONT_PREFERENCE = [
        "SF Pro Display",
        "SF Pro Text",
        "Inter",
        "Inter Variable",
        "Cantarell",
    ]

    # Ordered preference list of monospace fonts
    _MONO_FONT_PREFERENCE = [
        "SF Mono",
        "JetBrains Mono",
        "Fira Code",
        "Fira Mono",
        "Liberation Mono",
        "DejaVu Sans Mono",
    ]

    def __init__(self, base_size: int = 13) -> None:
        self._base_size = base_size
        self._installed: set[str] = set()
        self._resolved: FontConfig | None = None

    def load(self) -> FontConfig:
        """Detect fonts and resolve the configuration. Idempotent."""
        if self._resolved:
            return self._resolved
        self._installed = _fc_list_families()
        ui = self._pick(self._UI_FONT_PREFERENCE, "Cantarell")
        mono = self._pick(self._MONO_FONT_PREFERENCE, "monospace")
        logger.info("MacUX font: %r  mono: %r", ui, mono)

        self._resolved = FontConfig(
            ui_family=ui,
            ui_monospace=mono,
            ui_size=self._base_size,
            ui_size_sm=self._base_size - 2,
            ui_size_lg=self._base_size + 3,
            ui_size_xl=self._base_size + 8,
            weight_regular=400,
            weight_medium=500,
            weight_semibold=600,
            weight_bold=700,
            line_height=1.35,
            letter_spacing_tight=-0.01,
            letter_spacing_normal=0.0,
            letter_spacing_wide=0.03,
        )
        return self._resolved

    def _pick(self, preferences: list[str], fallback: str) -> str:
        for font in preferences:
            if font in self._installed:
                return font
        return fallback

    def get_css_font_stack(self) -> str:
        """Return a CSS font-family string with fallback chain."""
        cfg = self._resolved or self.load()
        families = [cfg.ui_family, "Cantarell", "sans-serif"]
        return ", ".join(f'"{f}"' if " " in f else f for f in families)

    def write_fontconfig(self) -> Path:
        """
        Write a fontconfig XML override so MacUX apps use the selected font
        as their default sans-serif. Returns the path written.
        """
        cfg = self._resolved or self.load()
        _FONTCONFIG_DIR.mkdir(parents=True, exist_ok=True)

        xml = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <!-- MacUX font override: maps generic families to chosen UI font -->
  <match target="pattern">
    <test qual="any" name="family"><string>sans-serif</string></test>
    <edit name="family" mode="prepend" binding="strong">
      <string>{cfg.ui_family}</string>
    </edit>
  </match>
  <match target="pattern">
    <test qual="any" name="family"><string>system-ui</string></test>
    <edit name="family" mode="prepend" binding="strong">
      <string>{cfg.ui_family}</string>
    </edit>
  </match>
  <!-- Enable sub-pixel antialiasing with LCD filter -->
  <match target="font">
    <edit name="antialias" mode="assign"><bool>true</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintslight</const></edit>
    <edit name="rgba" mode="assign"><const>rgb</const></edit>
    <edit name="lcdfilter" mode="assign"><const>lcddefault</const></edit>
  </match>
</fontconfig>
"""
        _FONTCONFIG_PATH.write_text(xml, encoding="utf-8")
        logger.info("Fontconfig written to %s", _FONTCONFIG_PATH)
        return _FONTCONFIG_PATH

    @property
    def config(self) -> FontConfig:
        return self._resolved or self.load()
