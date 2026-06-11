"""
MacUX Color System — semantic color tokens, accent derivation, contrast utilities.

Provides:
  - ColorPalette dataclass (all resolved color values for one theme variant)
  - AccentGenerator  (derives tints/shades from a single accent hex)
  - ContrastChecker  (WCAG 2.1 AA/AAA)
  - hex_to_rgb / rgb_to_hex / rgb_to_hsl / hsl_to_rgb utilities
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple


# ── Primitive color types ─────────────────────────────────────────────────────

class RGB(NamedTuple):
    r: float  # 0–1
    g: float
    b: float

    def to_hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(
            round(self.r * 255), round(self.g * 255), round(self.b * 255)
        )

    def to_rgba_str(self, alpha: float = 1.0) -> str:
        return "rgba({},{},{},{:.3f})".format(
            round(self.r * 255), round(self.g * 255), round(self.b * 255), alpha
        )

    def luminance(self) -> float:
        """Relative luminance for WCAG contrast calculation."""
        def lin(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(self.r) + 0.7152 * lin(self.g) + 0.0722 * lin(self.b)


class HSL(NamedTuple):
    h: float  # 0–360
    s: float  # 0–1
    l: float  # 0–1


def hex_to_rgb(hex_color: str) -> RGB:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return RGB(r, g, b)


def rgb_to_hsl(rgb: RGB) -> HSL:
    r, g, b = rgb
    cmax = max(r, g, b)
    cmin = min(r, g, b)
    delta = cmax - cmin
    l = (cmax + cmin) / 2

    if delta == 0:
        h = s = 0.0
    else:
        s = delta / (1 - abs(2 * l - 1))
        if cmax == r:
            h = 60 * (((g - b) / delta) % 6)
        elif cmax == g:
            h = 60 * ((b - r) / delta + 2)
        else:
            h = 60 * ((r - g) / delta + 4)

    return HSL(h % 360, s, l)


def hsl_to_rgb(hsl: HSL) -> RGB:
    h, s, l = hsl
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2

    if 0 <= h < 60:
        r, g, b = c, x, 0
    elif 60 <= h < 120:
        r, g, b = x, c, 0
    elif 120 <= h < 180:
        r, g, b = 0, c, x
    elif 180 <= h < 240:
        r, g, b = 0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return RGB(r + m, g + m, b + m)


def adjust_lightness(rgb: RGB, delta: float) -> RGB:
    """Add delta (−1..1) to the L channel in HSL space."""
    hsl = rgb_to_hsl(rgb)
    new_l = max(0.0, min(1.0, hsl.l + delta))
    return hsl_to_rgb(HSL(hsl.h, hsl.s, new_l))


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG 2.1 contrast ratio between two colors."""
    L1 = max(fg.luminance(), bg.luminance())
    L2 = min(fg.luminance(), bg.luminance())
    return (L1 + 0.05) / (L2 + 0.05)


def best_foreground(bg: RGB) -> RGB:
    """Return black or white, whichever contrasts better against bg."""
    white = RGB(1, 1, 1)
    black = RGB(0, 0, 0)
    return white if contrast_ratio(white, bg) >= contrast_ratio(black, bg) else black


# ── Accent generator ──────────────────────────────────────────────────────────

@dataclass
class AccentScale:
    """All accent-derived colors from a single base hex."""
    base: str           # e.g. "#0071e3"
    hover: str          # slightly lighter
    active: str         # slightly darker
    focus_ring: str     # accent at 50% opacity (as rgba string)
    subtle_bg: str      # very light tint (for highlight backgrounds)
    foreground: str     # black or white — best contrast on base


def generate_accent_scale(hex_color: str) -> AccentScale:
    base = hex_to_rgb(hex_color)
    hover = adjust_lightness(base, 0.06)
    active = adjust_lightness(base, -0.10)
    subtle = adjust_lightness(base, 0.42)

    return AccentScale(
        base=hex_color,
        hover=hover.to_hex(),
        active=active.to_hex(),
        focus_ring=base.to_rgba_str(0.5),
        subtle_bg=subtle.to_hex(),
        foreground=best_foreground(base).to_hex(),
    )


# ── Full color palette ────────────────────────────────────────────────────────

@dataclass
class ColorPalette:
    """
    Complete resolved color palette for one MacUX theme variant.
    All values are CSS-ready strings (hex or rgba()).
    """

    # Surface colors
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_hover: str
    bg_active: str
    bg_selected: str

    # Glass / translucency
    glass_bg: str
    glass_bg_strong: str
    glass_border: str
    glass_shadow: str

    # Text
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    text_on_accent: str

    # Accent (dynamically derived from config)
    accent: str
    accent_hover: str
    accent_active: str
    accent_focus_ring: str
    accent_subtle: str

    # Semantic
    destructive: str
    destructive_hover: str
    success: str
    warning: str

    # Borders / separators
    separator: str
    border: str
    border_strong: str

    # Dock-specific
    dock_bg: str
    dock_border: str
    dock_indicator: str
    dock_separator: str

    # Spotlight
    spotlight_bg: str
    spotlight_input_bg: str
    spotlight_result_hover: str
    spotlight_category_text: str

    # Launchpad
    launchpad_bg: str
    launchpad_folder_bg: str
    launchpad_label: str
    launchpad_page_dot: str
    launchpad_page_dot_active: str

    # Notification
    notification_bg: str
    notification_border: str
    notification_unread_dot: str

    # Control center
    control_bg: str
    control_toggle_on: str
    control_toggle_off: str
    control_slider_track: str

    # Scrollbars
    scrollbar_thumb: str
    scrollbar_thumb_hover: str

    @classmethod
    def light(cls, accent_hex: str = "#0071e3") -> "ColorPalette":
        acc = generate_accent_scale(accent_hex)
        return cls(
            # Surfaces
            bg_primary="#f5f5f7",
            bg_secondary="#ffffff",
            bg_tertiary="#f0f0f2",
            bg_hover="rgba(0,0,0,0.04)",
            bg_active="rgba(0,0,0,0.08)",
            bg_selected="rgba(0,113,227,0.12)",
            # Glass
            glass_bg="rgba(235,235,240,0.78)",
            glass_bg_strong="rgba(245,245,247,0.90)",
            glass_border="rgba(255,255,255,0.88)",
            glass_shadow="rgba(0,0,0,0.14)",
            # Text
            text_primary="#1d1d1f",
            text_secondary="#6e6e73",
            text_tertiary="#aeaeb2",
            text_disabled="#c7c7cc",
            text_on_accent=acc.foreground,
            # Accent
            accent=acc.base,
            accent_hover=acc.hover,
            accent_active=acc.active,
            accent_focus_ring=acc.focus_ring,
            accent_subtle=acc.subtle_bg,
            # Semantic
            destructive="#ff3b30",
            destructive_hover="#ff5147",
            success="#34c759",
            warning="#ff9500",
            # Borders
            separator="rgba(0,0,0,0.07)",
            border="rgba(0,0,0,0.10)",
            border_strong="rgba(0,0,0,0.20)",
            # Dock
            dock_bg="rgba(235,235,240,0.78)",
            dock_border="rgba(255,255,255,0.88)",
            dock_indicator="#1d1d1f",
            dock_separator="rgba(0,0,0,0.12)",
            # Spotlight
            spotlight_bg="rgba(235,235,240,0.90)",
            spotlight_input_bg="rgba(255,255,255,0.70)",
            spotlight_result_hover="rgba(0,0,0,0.05)",
            spotlight_category_text="#6e6e73",
            # Launchpad
            launchpad_bg="rgba(0,0,0,0.40)",
            launchpad_folder_bg="rgba(255,255,255,0.25)",
            launchpad_label="#ffffff",
            launchpad_page_dot="rgba(255,255,255,0.40)",
            launchpad_page_dot_active="rgba(255,255,255,0.90)",
            # Notification
            notification_bg="rgba(255,255,255,0.85)",
            notification_border="rgba(0,0,0,0.08)",
            notification_unread_dot=acc.base,
            # Control center
            control_bg="rgba(235,235,240,0.90)",
            control_toggle_on=acc.base,
            control_toggle_off="rgba(120,120,128,0.32)",
            control_slider_track="rgba(120,120,128,0.32)",
            # Scrollbars
            scrollbar_thumb="rgba(0,0,0,0.18)",
            scrollbar_thumb_hover="rgba(0,0,0,0.30)",
        )

    @classmethod
    def dark(cls, accent_hex: str = "#0a84ff") -> "ColorPalette":
        acc = generate_accent_scale(accent_hex)
        return cls(
            # Surfaces
            bg_primary="#1c1c1e",
            bg_secondary="#2c2c2e",
            bg_tertiary="#3a3a3c",
            bg_hover="rgba(255,255,255,0.05)",
            bg_active="rgba(255,255,255,0.10)",
            bg_selected="rgba(10,132,255,0.20)",
            # Glass
            glass_bg="rgba(28,28,30,0.78)",
            glass_bg_strong="rgba(44,44,46,0.90)",
            glass_border="rgba(255,255,255,0.12)",
            glass_shadow="rgba(0,0,0,0.50)",
            # Text
            text_primary="#f5f5f7",
            text_secondary="#aeaeb2",
            text_tertiary="#636366",
            text_disabled="#48484a",
            text_on_accent=acc.foreground,
            # Accent
            accent=acc.base,
            accent_hover=acc.hover,
            accent_active=acc.active,
            accent_focus_ring=acc.focus_ring,
            accent_subtle=acc.subtle_bg,
            # Semantic
            destructive="#ff453a",
            destructive_hover="#ff6961",
            success="#32d74b",
            warning="#ff9f0a",
            # Borders
            separator="rgba(255,255,255,0.08)",
            border="rgba(255,255,255,0.12)",
            border_strong="rgba(255,255,255,0.24)",
            # Dock
            dock_bg="rgba(28,28,30,0.80)",
            dock_border="rgba(255,255,255,0.14)",
            dock_indicator="#f5f5f7",
            dock_separator="rgba(255,255,255,0.12)",
            # Spotlight
            spotlight_bg="rgba(30,30,32,0.92)",
            spotlight_input_bg="rgba(58,58,60,0.80)",
            spotlight_result_hover="rgba(255,255,255,0.06)",
            spotlight_category_text="#aeaeb2",
            # Launchpad
            launchpad_bg="rgba(0,0,0,0.60)",
            launchpad_folder_bg="rgba(255,255,255,0.15)",
            launchpad_label="#ffffff",
            launchpad_page_dot="rgba(255,255,255,0.30)",
            launchpad_page_dot_active="rgba(255,255,255,0.80)",
            # Notification
            notification_bg="rgba(44,44,46,0.88)",
            notification_border="rgba(255,255,255,0.10)",
            notification_unread_dot=acc.base,
            # Control center
            control_bg="rgba(28,28,30,0.92)",
            control_toggle_on=acc.base,
            control_toggle_off="rgba(120,120,128,0.40)",
            control_slider_track="rgba(120,120,128,0.40)",
            # Scrollbars
            scrollbar_thumb="rgba(255,255,255,0.20)",
            scrollbar_thumb_hover="rgba(255,255,255,0.35)",
        )
