"""Unit tests for themes.colors — color math and palette generation."""

from __future__ import annotations

import pytest
from themes.colors import (
    RGB, HSL,
    hex_to_rgb, rgb_to_hsl, hsl_to_rgb,
    adjust_lightness, contrast_ratio,
    best_foreground, generate_accent_scale,
    ColorPalette,
)


class TestHexToRGB:
    def test_white(self):
        assert hex_to_rgb("#ffffff") == RGB(1.0, 1.0, 1.0)

    def test_black(self):
        r, g, b = hex_to_rgb("#000000")
        assert r == g == b == 0.0

    def test_apple_blue(self):
        r, g, b = hex_to_rgb("#0071e3")
        assert abs(r - 0/255) < 0.01
        assert abs(g - 113/255) < 0.01
        assert abs(b - 227/255) < 0.01

    def test_shorthand(self):
        assert hex_to_rgb("#fff") == hex_to_rgb("#ffffff")
        assert hex_to_rgb("#000") == hex_to_rgb("#000000")

    def test_no_hash_prefix(self):
        assert hex_to_rgb("ffffff") == RGB(1.0, 1.0, 1.0)


class TestHSLConversion:
    def test_white_hsl(self):
        hsl = rgb_to_hsl(RGB(1, 1, 1))
        assert hsl.l == pytest.approx(1.0)
        assert hsl.s == 0.0

    def test_black_hsl(self):
        hsl = rgb_to_hsl(RGB(0, 0, 0))
        assert hsl.l == 0.0

    def test_red_hsl(self):
        hsl = rgb_to_hsl(RGB(1, 0, 0))
        assert hsl.h == pytest.approx(0.0)
        assert hsl.s == pytest.approx(1.0)
        assert hsl.l == pytest.approx(0.5)

    def test_round_trip(self):
        original = RGB(0.2, 0.6, 0.9)
        converted = hsl_to_rgb(rgb_to_hsl(original))
        assert converted.r == pytest.approx(original.r, abs=0.001)
        assert converted.g == pytest.approx(original.g, abs=0.001)
        assert converted.b == pytest.approx(original.b, abs=0.001)

    def test_green_hsl(self):
        hsl = rgb_to_hsl(RGB(0, 1, 0))
        assert hsl.h == pytest.approx(120.0)

    def test_blue_hsl(self):
        hsl = rgb_to_hsl(RGB(0, 0, 1))
        assert hsl.h == pytest.approx(240.0)


class TestAdjustLightness:
    def test_lighten(self):
        blue = hex_to_rgb("#0071e3")
        lighter = adjust_lightness(blue, 0.2)
        orig_hsl = rgb_to_hsl(blue)
        new_hsl = rgb_to_hsl(lighter)
        assert new_hsl.l > orig_hsl.l

    def test_darken(self):
        blue = hex_to_rgb("#0071e3")
        darker = adjust_lightness(blue, -0.2)
        orig_hsl = rgb_to_hsl(blue)
        new_hsl = rgb_to_hsl(darker)
        assert new_hsl.l < orig_hsl.l

    def test_clamped_at_one(self):
        white = RGB(1, 1, 1)
        result = adjust_lightness(white, 0.5)
        assert rgb_to_hsl(result).l <= 1.0

    def test_clamped_at_zero(self):
        black = RGB(0, 0, 0)
        result = adjust_lightness(black, -0.5)
        assert rgb_to_hsl(result).l >= 0.0

    def test_hue_preserved(self):
        color = hex_to_rgb("#ff6000")
        orig_hue = rgb_to_hsl(color).h
        lightened = adjust_lightness(color, 0.1)
        new_hue = rgb_to_hsl(lightened).h
        assert abs(new_hue - orig_hue) < 1.0


class TestContrast:
    def test_black_on_white_max(self):
        ratio = contrast_ratio(RGB(0, 0, 0), RGB(1, 1, 1))
        assert ratio == pytest.approx(21.0, abs=0.1)

    def test_white_on_white_min(self):
        ratio = contrast_ratio(RGB(1, 1, 1), RGB(1, 1, 1))
        assert ratio == pytest.approx(1.0)

    def test_wcag_aa_4_5(self):
        # A dark text on white should easily pass AA (4.5:1)
        dark = hex_to_rgb("#1d1d1f")
        white = RGB(1, 1, 1)
        assert contrast_ratio(dark, white) >= 4.5

    def test_best_foreground_on_dark_returns_white(self):
        dark_bg = RGB(0.1, 0.1, 0.1)
        fg = best_foreground(dark_bg)
        assert fg.r == 1.0

    def test_best_foreground_on_light_returns_black(self):
        light_bg = RGB(0.95, 0.95, 0.95)
        fg = best_foreground(light_bg)
        assert fg.r == 0.0


class TestAccentScale:
    def test_scale_has_all_fields(self):
        scale = generate_accent_scale("#0071e3")
        assert scale.base == "#0071e3"
        assert scale.hover.startswith("#")
        assert scale.active.startswith("#")
        assert "rgba(" in scale.focus_ring
        assert scale.subtle_bg.startswith("#")
        assert scale.foreground in ("#ffffff", "#000000")

    def test_hover_lighter_than_base(self):
        scale = generate_accent_scale("#0071e3")
        base_l = rgb_to_hsl(hex_to_rgb(scale.base)).l
        hover_l = rgb_to_hsl(hex_to_rgb(scale.hover)).l
        assert hover_l > base_l

    def test_active_darker_than_base(self):
        scale = generate_accent_scale("#0071e3")
        base_l = rgb_to_hsl(hex_to_rgb(scale.base)).l
        active_l = rgb_to_hsl(hex_to_rgb(scale.active)).l
        assert active_l < base_l

    def test_dark_mode_accent(self):
        scale = generate_accent_scale("#0a84ff")
        assert scale.base == "#0a84ff"
        assert scale.foreground in ("#ffffff", "#000000")


class TestColorPalette:
    def test_light_palette_creates(self):
        p = ColorPalette.light("#0071e3")
        assert p.bg_primary == "#f5f5f7"
        assert p.accent == "#0071e3"
        assert p.text_primary == "#1d1d1f"

    def test_dark_palette_creates(self):
        p = ColorPalette.dark("#0a84ff")
        assert p.bg_primary == "#1c1c1e"
        assert p.accent == "#0a84ff"
        assert p.text_primary == "#f5f5f7"

    def test_custom_accent_applied(self):
        p = ColorPalette.light("#ff5500")
        assert p.accent == "#ff5500"

    def test_all_fields_non_empty(self):
        for variant_factory in (ColorPalette.light, ColorPalette.dark):
            p = variant_factory()
            for field_name, value in vars(p).items():
                assert value, f"Palette field {field_name!r} is empty in {variant_factory.__name__}"

    def test_glass_bg_has_alpha(self):
        p = ColorPalette.light()
        assert "rgba(" in p.glass_bg

    def test_dark_glass_bg_has_alpha(self):
        p = ColorPalette.dark()
        assert "rgba(" in p.glass_bg

    def test_rgb_to_hex_round_trip(self):
        original = "#4a90e2"
        rgb = hex_to_rgb(original)
        back = rgb.to_hex()
        assert back == original

    def test_rgba_string_format(self):
        rgb = RGB(1.0, 0.0, 0.5)
        s = rgb.to_rgba_str(0.75)
        assert s.startswith("rgba(")
        assert "0.750" in s
