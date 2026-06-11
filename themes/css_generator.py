"""
MacUX CSS Generator — builds GTK4 CSS strings from a ColorPalette + FontConfig.

Generates:
  - Color definitions block (@define-color for GTK4/Adwaita compatibility)
  - Typography block (font-family, sizes as CSS custom properties)
  - Design token block (spacing, radius, shadow, animation durations)
  - Per-component CSS (returned as individual strings for targeted loading)
"""

from __future__ import annotations

import logging
from pathlib import Path

from themes.colors import ColorPalette
from themes.font_manager import FontConfig

logger = logging.getLogger(__name__)

_CSS_DIR = Path(__file__).parent / "gtk4"


def load_css_file(name: str) -> str:
    """Load a CSS file from themes/gtk4/, returning empty string if missing."""
    path = _CSS_DIR / name
    if not path.exists():
        logger.warning("CSS file not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def load_component_css(component: str) -> str:
    """Load themes/gtk4/components/<component>.css"""
    return load_css_file(f"components/{component}.css")


class CSSGenerator:
    """
    Builds complete GTK4 CSS strings from resolved design tokens.

    Usage:
        gen = CSSGenerator(palette, font_config)
        full_css = gen.build_full()       # everything combined
        dock_css = gen.build_component("dock")  # tokens + dock.css
    """

    def __init__(self, palette: ColorPalette, fonts: FontConfig) -> None:
        self.palette = palette
        self.fonts = fonts

    # ── Public API ────────────────────────────────────────────────────────────

    def build_full(self) -> str:
        """Build the complete CSS for all MacUX components."""
        parts = [
            self._header(),
            self._color_definitions(),
            self._typography_tokens(),
            self._design_tokens(),
            load_css_file("base.css"),
            load_css_file("animations.css"),
            load_css_file("components/common.css"),
        ]
        return "\n\n".join(p for p in parts if p)

    def build_component(self, component: str) -> str:
        """Build CSS for a specific component (tokens + component-specific CSS)."""
        parts = [
            self._header(),
            self._color_definitions(),
            self._typography_tokens(),
            self._design_tokens(),
            load_component_css(component),
        ]
        return "\n\n".join(p for p in parts if p)

    def build_gnome_shell(self, variant: str = "light") -> str:
        """Build GNOME Shell CSS with dynamic color substitution."""
        path = Path(__file__).parent / "gnome-shell" / f"gnome-shell-{variant}.css"
        if not path.exists():
            logger.warning("GNOME Shell CSS not found: %s", path)
            return ""
        template = path.read_text(encoding="utf-8")
        # Substitute color tokens into the template
        return self._substitute_tokens(template)

    # ── Color definitions block ───────────────────────────────────────────────

    def _color_definitions(self) -> str:
        p = self.palette
        lines = [
            "/* ── MacUX Color Tokens ── */",
            # Surfaces
            f"@define-color macux_bg_primary         {p.bg_primary};",
            f"@define-color macux_bg_secondary        {p.bg_secondary};",
            f"@define-color macux_bg_tertiary         {p.bg_tertiary};",
            f"@define-color macux_bg_hover            {p.bg_hover};",
            f"@define-color macux_bg_active           {p.bg_active};",
            f"@define-color macux_bg_selected         {p.bg_selected};",
            # Glass
            f"@define-color macux_glass_bg            {p.glass_bg};",
            f"@define-color macux_glass_bg_strong     {p.glass_bg_strong};",
            f"@define-color macux_glass_border        {p.glass_border};",
            f"@define-color macux_glass_shadow        {p.glass_shadow};",
            # Text
            f"@define-color macux_text_primary        {p.text_primary};",
            f"@define-color macux_text_secondary      {p.text_secondary};",
            f"@define-color macux_text_tertiary       {p.text_tertiary};",
            f"@define-color macux_text_disabled       {p.text_disabled};",
            f"@define-color macux_text_on_accent      {p.text_on_accent};",
            # Accent
            f"@define-color macux_accent              {p.accent};",
            f"@define-color macux_accent_hover        {p.accent_hover};",
            f"@define-color macux_accent_active       {p.accent_active};",
            f"@define-color macux_accent_subtle       {p.accent_subtle};",
            # Semantic
            f"@define-color macux_destructive         {p.destructive};",
            f"@define-color macux_destructive_hover   {p.destructive_hover};",
            f"@define-color macux_success             {p.success};",
            f"@define-color macux_warning             {p.warning};",
            # Structure
            f"@define-color macux_separator           {p.separator};",
            f"@define-color macux_border              {p.border};",
            f"@define-color macux_border_strong       {p.border_strong};",
            # Dock
            f"@define-color macux_dock_bg             {p.dock_bg};",
            f"@define-color macux_dock_border         {p.dock_border};",
            f"@define-color macux_dock_indicator      {p.dock_indicator};",
            f"@define-color macux_dock_separator      {p.dock_separator};",
            # Spotlight
            f"@define-color macux_spotlight_bg        {p.spotlight_bg};",
            f"@define-color macux_spotlight_input_bg  {p.spotlight_input_bg};",
            f"@define-color macux_spotlight_hover     {p.spotlight_result_hover};",
            f"@define-color macux_spotlight_cat_text  {p.spotlight_category_text};",
            # Launchpad
            f"@define-color macux_launchpad_bg        {p.launchpad_bg};",
            f"@define-color macux_launchpad_folder_bg {p.launchpad_folder_bg};",
            f"@define-color macux_launchpad_label     {p.launchpad_label};",
            f"@define-color macux_launchpad_dot       {p.launchpad_page_dot};",
            f"@define-color macux_launchpad_dot_active {p.launchpad_page_dot_active};",
            # Notification
            f"@define-color macux_notification_bg     {p.notification_bg};",
            f"@define-color macux_notification_border {p.notification_border};",
            f"@define-color macux_notif_unread        {p.notification_unread_dot};",
            # Control Center
            f"@define-color macux_control_bg          {p.control_bg};",
            f"@define-color macux_control_toggle_on   {p.control_toggle_on};",
            f"@define-color macux_control_toggle_off  {p.control_toggle_off};",
            f"@define-color macux_control_track       {p.control_slider_track};",
            # Scrollbars
            f"@define-color macux_scrollbar_thumb     {p.scrollbar_thumb};",
            f"@define-color macux_scrollbar_thumb_h   {p.scrollbar_thumb_hover};",
        ]
        return "\n".join(lines)

    def _typography_tokens(self) -> str:
        f = self.fonts
        stack = self._font_stack()
        return f"""/* ── MacUX Typography Tokens ── */
* {{
  --macux-font-family: {stack};
  --macux-font-mono:   "{f.ui_monospace}", monospace;
  --macux-font-size:   {f.ui_size}pt;
  --macux-font-sm:     {f.ui_size_sm}pt;
  --macux-font-lg:     {f.ui_size_lg}pt;
  --macux-font-xl:     {f.ui_size_xl}pt;
  --macux-weight-regular:  {f.weight_regular};
  --macux-weight-medium:   {f.weight_medium};
  --macux-weight-semibold: {f.weight_semibold};
  --macux-weight-bold:     {f.weight_bold};
  --macux-line-height: {f.line_height};
  --macux-tracking-tight:  {f.letter_spacing_tight}em;
  --macux-tracking-normal: {f.letter_spacing_normal}em;
  --macux-tracking-wide:   {f.letter_spacing_wide}em;
}}"""

    def _design_tokens(self) -> str:
        return """/* ── MacUX Design Tokens ── */
* {
  /* Spacing scale (4pt grid) */
  --macux-space-1:   4px;
  --macux-space-2:   8px;
  --macux-space-3:  12px;
  --macux-space-4:  16px;
  --macux-space-5:  20px;
  --macux-space-6:  24px;
  --macux-space-8:  32px;
  --macux-space-10: 40px;
  --macux-space-12: 48px;
  --macux-space-16: 64px;

  /* Border radii */
  --macux-radius-xs:   4px;
  --macux-radius-sm:   6px;
  --macux-radius-md:  10px;
  --macux-radius-lg:  14px;
  --macux-radius-xl:  20px;
  --macux-radius-2xl: 28px;
  --macux-radius-full: 9999px;

  /* Shadows */
  --macux-shadow-xs:  0 1px 2px @macux_glass_shadow;
  --macux-shadow-sm:  0 2px 6px @macux_glass_shadow;
  --macux-shadow-md:  0 4px 16px @macux_glass_shadow;
  --macux-shadow-lg:  0 8px 32px @macux_glass_shadow;
  --macux-shadow-xl:  0 16px 56px @macux_glass_shadow;
  --macux-shadow-dock: 0 8px 40px rgba(0,0,0,0.22), 0 2px 8px rgba(0,0,0,0.14);

  /* Animation durations */
  --macux-dur-instant: 80ms;
  --macux-dur-fast:   150ms;
  --macux-dur-normal: 250ms;
  --macux-dur-slow:   400ms;
  --macux-dur-slower: 600ms;

  /* Animation easings */
  --macux-ease-spring:     cubic-bezier(0.34, 1.56, 0.64, 1.00);
  --macux-ease-out:        cubic-bezier(0.16, 1.00, 0.30, 1.00);
  --macux-ease-in-out:     cubic-bezier(0.65, 0.00, 0.35, 1.00);
  --macux-ease-bounce:     cubic-bezier(0.68, -0.55, 0.27, 1.55);

  /* Dock dimensions */
  --macux-dock-height:         72px;
  --macux-dock-icon-size:      48px;
  --macux-dock-icon-max:       72px;
  --macux-dock-padding-h:      12px;
  --macux-dock-padding-v:       8px;
  --macux-dock-radius:         18px;
  --macux-dock-indicator-size:  4px;

  /* Menu bar */
  --macux-menubar-height:      28px;

  /* Spotlight */
  --macux-spotlight-width:    680px;
  --macux-spotlight-radius:   14px;
  --macux-spotlight-icon-size: 36px;
}"""

    def _font_stack(self) -> str:
        primary = self.fonts.ui_family
        parts = [f'"{primary}"' if " " in primary else primary]
        # Always include Cantarell as fallback if primary isn't already Cantarell
        if primary != "Cantarell":
            parts.append('"Cantarell"')
        parts.append("sans-serif")
        return ", ".join(parts)

    def _header(self) -> str:
        return "/* MacUX GTK4 Theme — auto-generated by ThemeEngine — do not edit */"

    def _substitute_tokens(self, template: str) -> str:
        """Replace {{TOKEN}} placeholders in GNOME Shell CSS templates."""
        p = self.palette
        substitutions = {
            "{{ACCENT}}": p.accent,
            "{{BG_PRIMARY}}": p.bg_primary,
            "{{BG_SECONDARY}}": p.bg_secondary,
            "{{GLASS_BG}}": p.glass_bg,
            "{{GLASS_BORDER}}": p.glass_border,
            "{{TEXT_PRIMARY}}": p.text_primary,
            "{{TEXT_SECONDARY}}": p.text_secondary,
            "{{SEPARATOR}}": p.separator,
            "{{FONT_FAMILY}}": self._font_stack(),
        }
        for token, value in substitutions.items():
            template = template.replace(token, value)
        return template
