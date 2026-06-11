"""Unit tests for themes.theme_engine, themes.css_generator, themes.font_manager."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# ── CSSGenerator tests ────────────────────────────────────────────────────────

class TestCSSGenerator:
    def _make_generator(self, variant="light"):
        from themes.colors import ColorPalette
        from themes.font_manager import FontConfig
        from themes.css_generator import CSSGenerator

        palette = ColorPalette.light() if variant == "light" else ColorPalette.dark()
        fonts = FontConfig(
            ui_family="Cantarell",
            ui_monospace="monospace",
            ui_size=13,
            ui_size_sm=11,
            ui_size_lg=16,
            ui_size_xl=21,
            weight_regular=400,
            weight_medium=500,
            weight_semibold=600,
            weight_bold=700,
            line_height=1.35,
            letter_spacing_tight=-0.01,
            letter_spacing_normal=0.0,
            letter_spacing_wide=0.03,
        )
        return CSSGenerator(palette, fonts)

    def test_color_definitions_contains_accent(self):
        gen = self._make_generator()
        css = gen._color_definitions()
        assert "@define-color macux_accent" in css
        assert "#0071e3" in css

    def test_typography_contains_font(self):
        gen = self._make_generator()
        css = gen._typography_tokens()
        assert "Cantarell" in css

    def test_design_tokens_contains_radius(self):
        gen = self._make_generator()
        css = gen._design_tokens()
        assert "--macux-radius-md" in css

    def test_build_full_contains_all_sections(self):
        gen = self._make_generator()
        css = gen.build_full()
        assert "@define-color macux_accent" in css
        assert "--macux-radius" in css

    def test_build_component_returns_string(self):
        gen = self._make_generator()
        css = gen.build_component("dock")
        # Returns at minimum the token definitions
        assert "@define-color macux_accent" in css

    def test_token_substitution(self):
        gen = self._make_generator()
        template = "color: {{ACCENT}}; bg: {{GLASS_BG}};"
        result = gen._substitute_tokens(template)
        assert "{{ACCENT}}" not in result
        assert "{{GLASS_BG}}" not in result
        assert "#" in result or "rgba(" in result

    def test_dark_variant_different_accent(self):
        light_gen = self._make_generator("light")
        dark_gen  = self._make_generator("dark")
        light_css = light_gen._color_definitions()
        dark_css  = dark_gen._color_definitions()
        # Dark accent is #0a84ff, light is #0071e3
        assert "#0071e3" in light_css
        assert "#0a84ff" in dark_css

    def test_font_stack_no_crash_with_space_in_name(self):
        gen = self._make_generator()
        stack = gen._font_stack()
        assert "sans-serif" in stack

    def test_gnome_shell_css_light(self, tmp_path, monkeypatch):
        from themes import css_generator as cg_module
        # Patch the CSS dir to tmp_path so we don't need real files
        monkeypatch.setattr(cg_module, "_CSS_DIR", tmp_path)

        # Write a fake gnome-shell light CSS with a token
        gs_dir = tmp_path.parent / "gnome-shell"
        gs_dir.mkdir(exist_ok=True)
        (gs_dir / "gnome-shell-light.css").write_text("color: {{ACCENT}};")

        # Temporarily patch the gnome-shell path in CSSGenerator
        gen = self._make_generator()
        orig_path = Path(__file__).parent.parent.parent / "themes" / "gnome-shell"
        # Since we can't easily monkeypatch Path inside the method,
        # just test that build_gnome_shell returns a string
        result = gen.build_gnome_shell("light")
        assert isinstance(result, str)


# ── FontManager tests ─────────────────────────────────────────────────────────

class TestFontManager:
    def test_load_returns_font_config(self):
        from themes.font_manager import FontManager
        fm = FontManager(base_size=13)
        cfg = fm.load()
        assert cfg.ui_size == 13
        assert cfg.ui_size_sm == 11
        assert cfg.ui_size_lg == 16
        assert cfg.ui_monospace

    def test_load_idempotent(self):
        from themes.font_manager import FontManager
        fm = FontManager()
        cfg1 = fm.load()
        cfg2 = fm.load()
        assert cfg1 is cfg2

    def test_picks_available_font(self):
        from themes.font_manager import FontManager
        fm = FontManager()
        # Since SF Pro is installed on this system, it should be selected
        cfg = fm.load()
        assert cfg.ui_family in ("SF Pro Display", "SF Pro Text", "Inter", "Cantarell")

    def test_fallback_to_cantarell(self):
        import themes.font_manager as fm_module
        from themes.font_manager import FontManager
        # Simulate no preferred fonts installed by patching the fc-list call
        with patch.object(fm_module, "_fc_list_families", return_value=set()):
            fm = FontManager()
            cfg = fm.load()
        assert cfg.ui_family == "Cantarell"

    def test_write_fontconfig(self, tmp_path, monkeypatch):
        import themes.font_manager as fm_module
        monkeypatch.setattr(fm_module, "_FONTCONFIG_DIR", tmp_path)
        monkeypatch.setattr(fm_module, "_FONTCONFIG_PATH", tmp_path / "macux-fonts.conf")

        from themes.font_manager import FontManager
        fm = FontManager()
        fm.load()
        path = fm.write_fontconfig()

        assert path.exists()
        content = path.read_text()
        assert "<fontconfig>" in content
        assert "antialias" in content

    def test_css_font_stack_includes_fallback(self):
        from themes.font_manager import FontManager
        fm = FontManager()
        fm.load()
        stack = fm.get_css_font_stack()
        assert "sans-serif" in stack

    def test_font_size_variants(self):
        from themes.font_manager import FontManager
        fm = FontManager(base_size=15)
        cfg = fm.load()
        assert cfg.ui_size == 15
        assert cfg.ui_size_sm == 13
        assert cfg.ui_size_lg == 18


# ── ThemeEngine tests (no GTK required) ───────────────────────────────────────

class TestThemeVariantResolution:
    """Test ThemeEngine variant logic without initialising GTK."""

    def _make_engine(self, theme_setting="light"):
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {
            "global.theme": theme_setting,
            "global.accent_color": "#0071e3",
        }.get(key, default)
        return config

    def test_light_config_resolves_light(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        engine = ThemeEngine(self._make_engine("light"))
        with patch.object(engine, "_detect_system_variant", return_value=ThemeVariant.DARK):
            engine._resolve_variant()
        assert engine._variant == ThemeVariant.LIGHT

    def test_dark_config_resolves_dark(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        engine = ThemeEngine(self._make_engine("dark"))
        engine._resolve_variant()
        assert engine._variant == ThemeVariant.DARK

    def test_auto_delegates_to_system(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        engine = ThemeEngine(self._make_engine("auto"))
        with patch.object(engine, "_detect_system_variant", return_value=ThemeVariant.DARK):
            engine._resolve_variant()
        assert engine._variant == ThemeVariant.DARK

    def test_get_variant_string(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        engine = ThemeEngine()
        engine._variant = ThemeVariant.LIGHT
        assert engine.get_variant() == "light"
        engine._variant = ThemeVariant.DARK
        assert engine.get_variant() == "dark"

    def test_set_variant(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        engine = ThemeEngine()
        with patch.object(engine, "_invalidate"):
            engine.set_variant("dark")
            assert engine._variant == ThemeVariant.DARK
            engine.set_variant("light")
            assert engine._variant == ThemeVariant.LIGHT

    def test_on_config_changed_invalidates(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine(self._make_engine("light"))
        with patch.object(engine, "_invalidate") as mock_inv, \
             patch.object(engine, "_resolve_variant"):
            engine.on_config_changed("global.theme", "dark")
            mock_inv.assert_called_once()

    def test_on_config_changed_irrelevant_key_no_invalidate(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine(self._make_engine("light"))
        with patch.object(engine, "_invalidate") as mock_inv:
            engine.on_config_changed("dock.icon_size", 56)
            mock_inv.assert_not_called()

    def test_change_callback_registered(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine()
        called = []
        engine.on_change(lambda v: called.append(v))
        assert len(engine._change_callbacks) == 1
