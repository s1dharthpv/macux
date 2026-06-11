"""
MacUX ThemeEngine — the central runtime theming system.

Responsibilities:
  1. Resolve the active theme variant (light | dark | auto)
  2. Generate complete CSS via CSSGenerator
  3. Apply CSS to every GTK4 window via Gtk.CssProvider
  4. React to:
       - config changes (accent_color, theme, font_size)
       - GNOME color scheme changes (Adw.StyleManager for auto mode)
  5. Provide per-component CSS loaders for lazy application

Thread safety: all GTK operations must be called from the GLib main thread.
              Use GLib.idle_add() when calling from background threads.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk

from themes.colors import ColorPalette
from themes.css_generator import CSSGenerator
from themes.font_manager import FontManager

logger = logging.getLogger(__name__)

ThemeChangeCallback = Callable[[str], None]  # receives "light" or "dark"


class ThemeVariant(Enum):
    LIGHT = auto()
    DARK = auto()


class ThemeEngine:
    """
    Runtime GTK4 theme manager.

    Usage (from an Adw.Application):

        engine = ThemeEngine(config_manager)
        engine.init()                    # call after Adw.Application.run() starts
        engine.apply_to_display()        # apply to the default display
    """

    def __init__(self, config=None) -> None:
        self._config = config
        self._font_manager = FontManager()
        self._provider: Gtk.CssProvider | None = None
        self._component_providers: dict[str, Gtk.CssProvider] = {}
        self._variant: ThemeVariant = ThemeVariant.LIGHT
        self._palette: ColorPalette | None = None
        self._generator: CSSGenerator | None = None
        self._change_callbacks: list[ThemeChangeCallback] = []
        self._style_manager: Adw.StyleManager | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def init(self) -> None:
        """
        Initialise the theme engine. Must be called from the GLib main thread
        after Adw.Application is running (i.e. inside 'activate' signal handler).
        """
        self._font_manager.load()
        self._font_manager.write_fontconfig()
        self._resolve_variant()
        self._build_css()
        self._connect_style_manager()
        logger.info("ThemeEngine initialised — variant=%s", self._variant.name)

    def apply_to_display(self, display: Gdk.Display | None = None) -> None:
        """
        Apply the MacUX CSS to a GTK4 display (default: Gdk.Display.get_default()).
        Safe to call multiple times; replaces the previous provider.
        """
        if display is None:
            display = Gdk.Display.get_default()
        if display is None:
            logger.error("No GDK display available — cannot apply CSS")
            return

        css = self._build_css()
        if self._provider:
            Gtk.StyleContext.remove_provider_for_display(display, self._provider)

        self._provider = Gtk.CssProvider()
        self._provider.connect("parsing-error", self._on_css_error)
        self._provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            display,
            self._provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        logger.debug("CSS applied to display (%d bytes)", len(css))

    def apply_component_css(self, component: str, display: Gdk.Display | None = None) -> None:
        """Apply CSS for a specific component — use for lazy per-window loading."""
        if display is None:
            display = Gdk.Display.get_default()
        if not display:
            return

        generator = self._get_generator()
        css = generator.build_component(component)

        old = self._component_providers.get(component)
        if old:
            Gtk.StyleContext.remove_provider_for_display(display, old)

        provider = Gtk.CssProvider()
        provider.connect("parsing-error", self._on_css_error)
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._component_providers[component] = provider

    def get_color(self, token: str) -> str:
        """Return the resolved CSS color value for a palette token name."""
        palette = self._get_palette()
        return getattr(palette, token, "#000000")

    def get_variant(self) -> str:
        return "dark" if self._variant == ThemeVariant.DARK else "light"

    def set_variant(self, variant: str) -> None:
        """Force light or dark. Overrides 'auto' until config is changed."""
        new = ThemeVariant.DARK if variant == "dark" else ThemeVariant.LIGHT
        if new != self._variant:
            self._variant = new
            self._invalidate()

    def on_change(self, callback: ThemeChangeCallback) -> None:
        self._change_callbacks.append(callback)

    def get_gnome_shell_css(self, variant: str | None = None) -> str:
        """Return generated GNOME Shell CSS for the given or current variant."""
        generator = self._get_generator()
        return generator.build_gnome_shell(variant or self.get_variant())

    def build_full_css(self) -> str:
        """Return the full GTK4 CSS for the current variant (no display required)."""
        return self._get_generator().build_full()

    def build_component_css(self, component: str) -> str:
        """Return CSS for a named component (e.g. 'dock', 'spotlight')."""
        return self._get_generator().build_component(component)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_variant(self) -> None:
        """Determine light/dark from config + Adw.StyleManager."""
        configured = "auto"
        if self._config:
            configured = self._config.get("global.theme", "auto")

        if configured == "dark":
            self._variant = ThemeVariant.DARK
        elif configured == "light":
            self._variant = ThemeVariant.LIGHT
        else:
            # Auto: follow GNOME's color scheme
            self._variant = self._detect_system_variant()

    def _detect_system_variant(self) -> ThemeVariant:
        try:
            manager = Adw.StyleManager.get_default()
            scheme = manager.get_color_scheme()
            is_dark = manager.get_dark()
            return ThemeVariant.DARK if is_dark else ThemeVariant.LIGHT
        except Exception:
            return ThemeVariant.LIGHT

    def _connect_style_manager(self) -> None:
        """Connect to Adw.StyleManager for auto-theme tracking."""
        try:
            self._style_manager = Adw.StyleManager.get_default()
            self._style_manager.connect("notify::dark", self._on_system_theme_changed)
            logger.debug("Connected to Adw.StyleManager for auto-theme tracking.")
        except Exception:
            logger.debug("Adw.StyleManager not available; auto-theme disabled.")

    def _on_system_theme_changed(self, manager: Adw.StyleManager, _pspec) -> None:
        configured = "auto"
        if self._config:
            configured = self._config.get("global.theme", "auto")
        if configured != "auto":
            return  # user has explicit preference, ignore system change
        new_variant = ThemeVariant.DARK if manager.get_dark() else ThemeVariant.LIGHT
        if new_variant != self._variant:
            logger.info("System theme changed → %s", new_variant.name)
            self._variant = new_variant
            self._invalidate()

    def _get_accent(self) -> str:
        if self._config:
            accent = self._config.get("global.accent_color")
            if accent:
                return accent
        return "#0a84ff" if self._variant == ThemeVariant.DARK else "#0071e3"

    def _get_palette(self) -> ColorPalette:
        if self._palette is None:
            accent = self._get_accent()
            if self._variant == ThemeVariant.DARK:
                self._palette = ColorPalette.dark(accent)
            else:
                self._palette = ColorPalette.light(accent)
        return self._palette

    def _get_generator(self) -> CSSGenerator:
        if self._generator is None:
            self._generator = CSSGenerator(self._get_palette(), self._font_manager.config)
        return self._generator

    def _build_css(self) -> str:
        return self._get_generator().build_full()

    def _invalidate(self) -> None:
        """Invalidate cached palette/generator, re-apply CSS, notify subscribers."""
        self._palette = None
        self._generator = None
        GLib.idle_add(self._reapply)

    def _reapply(self) -> bool:
        self.apply_to_display()
        variant_name = self.get_variant()
        for cb in self._change_callbacks:
            try:
                cb(variant_name)
            except Exception:
                logger.exception("ThemeEngine change callback raised")
        return GLib.SOURCE_REMOVE

    def on_config_changed(self, key: str, value) -> None:
        """Wire this to ConfigManager.on_change() for automatic theme updates."""
        if key in ("global.theme", "global.accent_color", "global.font_size"):
            self._resolve_variant()
            if key == "global.font_size" and self._config:
                self._font_manager._base_size = int(self._config.get("global.font_size", 13))
                self._font_manager._resolved = None
                self._font_manager.load()
            self._invalidate()

    @staticmethod
    def _on_css_error(provider, section, error) -> None:
        logger.error(
            "CSS parse error at %s:%d — %s",
            section.get_file(),
            section.get_start_location().lines + 1,
            error.message,
        )
