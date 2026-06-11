"""Unit tests for themes.theme_installer and macuxd.ctl."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_installer(tmp_path: Path, engine=None):
    """Create a ThemeInstaller pointed at a tmp source directory."""
    import themes.theme_installer as ti_module
    from themes.theme_installer import ThemeInstaller

    # Build minimal source tree in tmp_path
    (tmp_path / "themes" / "icons" / "MacUX").mkdir(parents=True)
    (tmp_path / "themes" / "icons" / "MacUX" / "index.theme").write_text("[Icon Theme]\nName=MacUX\n")
    (tmp_path / "themes" / "cursors" / "MacUX").mkdir(parents=True)
    (tmp_path / "themes" / "cursors" / "MacUX" / "index.theme").write_text("[Icon Theme]\nName=MacUX-Cursors\n")
    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    (tmp_path / "assets" / "fonts" / "fonts.conf").write_text(
        "<?xml version='1.0'?><fontconfig></fontconfig>"
    )
    (tmp_path / "gnome-extensions" / "macux-shell@macux.com" / "schemas").mkdir(parents=True)
    (tmp_path / "gnome-extensions" / "macux-shell@macux.com" / "schemas" /
     "org.gnome.shell.extensions.macux.gschema.xml").write_text(
        '<schemalist><schema id="org.gnome.shell.extensions.macux" path="/org/gnome/shell/extensions/macux/"></schema></schemalist>'
    )
    (tmp_path / "themes" / "gnome-shell").mkdir(parents=True)
    (tmp_path / "themes" / "gnome-shell" / "gnome-shell-light.css").write_text("color: {{ACCENT}};")
    (tmp_path / "themes" / "gnome-shell" / "gnome-shell-dark.css").write_text("color: {{ACCENT}};")

    return ThemeInstaller(source_dir=tmp_path, theme_engine=engine)


# ── ThemeInstaller ─────────────────────────────────────────────────────────────

class TestThemeInstallerGTK:
    """Tests for GTK4 CSS installation."""

    def test_install_gtk_theme_writes_css(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        gtk_theme_dir = tmp_path / "out" / "themes" / "MacUX" / "gtk-4.0"
        gtk_user_dir = tmp_path / "out" / "gtk4-user"

        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", gtk_theme_dir)
        monkeypatch.setattr(ti_module, "_GTK4_USER_DIR", gtk_user_dir)
        monkeypatch.setattr(ti_module, "_GTK4_USER_CSS", gtk_user_dir / "gtk.css")

        engine = MagicMock()
        engine.build_full_css.return_value = ".macux { color: red; }"

        installer = _make_installer(tmp_path, engine=engine)
        paths = installer.install_gtk_theme()

        assert len(paths) == 2
        assert (gtk_theme_dir / "gtk.css").read_text() == ".macux { color: red; }"
        assert (gtk_user_dir / "gtk.css").read_text() == ".macux { color: red; }"

    def test_install_gtk_theme_no_engine_uses_base_css(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        gtk_theme_dir = tmp_path / "out" / "gtk-4.0"
        gtk_user_dir = tmp_path / "out" / "gtk4-user"
        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", gtk_theme_dir)
        monkeypatch.setattr(ti_module, "_GTK4_USER_DIR", gtk_user_dir)
        monkeypatch.setattr(ti_module, "_GTK4_USER_CSS", gtk_user_dir / "gtk.css")

        # Write a fake base.css in the source tree
        gtk4_src = tmp_path / "themes" / "gtk4"
        gtk4_src.mkdir(parents=True)
        (gtk4_src / "base.css").write_text("/* base */")

        installer = _make_installer(tmp_path)  # no engine
        paths = installer.install_gtk_theme()

        assert any(p.name == "gtk.css" for p in paths)


class TestThemeInstallerIcons:
    def test_install_icon_theme_copies_directory(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        icon_dest = tmp_path / "icons" / "MacUX"
        monkeypatch.setattr(ti_module, "_ICON_THEME_DIR", icon_dest)
        monkeypatch.setattr(ti_module, "_SRC_ICONS", tmp_path / "themes" / "icons" / "MacUX")

        installer = _make_installer(tmp_path)
        paths = installer.install_icon_theme()

        assert icon_dest.is_dir()
        assert (icon_dest / "index.theme").exists()
        assert paths[0] == icon_dest

    def test_install_icon_theme_missing_source_raises(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        monkeypatch.setattr(ti_module, "_SRC_ICONS", tmp_path / "nonexistent")
        monkeypatch.setattr(ti_module, "_ICON_THEME_DIR", tmp_path / "out")

        with pytest.raises(FileNotFoundError):
            _make_installer(tmp_path).install_icon_theme()

    def test_install_cursor_theme_copies_index(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        cursor_dest = tmp_path / "icons" / "MacUX-Cursors"
        monkeypatch.setattr(ti_module, "_CURSOR_THEME_DIR", cursor_dest)
        monkeypatch.setattr(ti_module, "_SRC_CURSORS", tmp_path / "themes" / "cursors" / "MacUX")

        installer = _make_installer(tmp_path)
        paths = installer.install_cursor_theme()

        assert (cursor_dest / "index.theme").exists()
        assert "MacUX-Cursors" in (cursor_dest / "index.theme").read_text()


class TestThemeInstallerFontconfig:
    def test_install_fontconfig_copies_conf(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        fc_dir = tmp_path / "fontconfig" / "conf.d"
        fc_path = fc_dir / "90-macux.conf"
        monkeypatch.setattr(ti_module, "_FONTCONFIG_DIR", fc_dir)
        monkeypatch.setattr(ti_module, "_FONTCONFIG_PATH", fc_path)
        monkeypatch.setattr(ti_module, "_SRC_FONTS_CONF", tmp_path / "assets" / "fonts" / "fonts.conf")

        installer = _make_installer(tmp_path)
        paths = installer.install_fontconfig()

        assert fc_path.exists()
        assert "fontconfig" in fc_path.read_text()
        assert paths == [fc_path]

    def test_install_fontconfig_missing_source_raises(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        monkeypatch.setattr(ti_module, "_SRC_FONTS_CONF", tmp_path / "nonexistent.conf")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_DIR", tmp_path / "out")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_PATH", tmp_path / "out" / "90-macux.conf")

        with pytest.raises(FileNotFoundError):
            _make_installer(tmp_path).install_fontconfig()


class TestThemeInstallerGnomeShell:
    def test_install_gnome_shell_css_no_engine_copies_templates(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        dest_dir = tmp_path / "gnome-shell"
        monkeypatch.setattr(ti_module, "_GNOME_SHELL_THEME_DIR", dest_dir)
        monkeypatch.setattr(ti_module, "_SRC_THEMES", tmp_path / "themes")

        installer = _make_installer(tmp_path)
        paths = installer.install_gnome_shell_theme()

        assert dest_dir.is_dir()
        # Should have at least one .css file
        css_files = list(dest_dir.glob("*.css"))
        assert len(css_files) >= 1

    def test_install_gnome_shell_css_with_engine_uses_generated(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        dest_dir = tmp_path / "gnome-shell-out"
        monkeypatch.setattr(ti_module, "_GNOME_SHELL_THEME_DIR", dest_dir)

        engine = MagicMock()
        engine.get_gnome_shell_css.return_value = "/* generated */"

        installer = _make_installer(tmp_path, engine=engine)
        paths = installer.install_gnome_shell_theme()

        # Engine called for both variants
        assert engine.get_gnome_shell_css.call_count == 2
        calls = [c.args[0] for c in engine.get_gnome_shell_css.call_args_list]
        assert "light" in calls
        assert "dark" in calls

        # All CSS files contain generated content
        for p in paths:
            if p.suffix == ".css":
                assert "generated" in p.read_text()


class TestThemeInstallerSchema:
    def test_compile_gsettings_schema_copies_and_compiles(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        monkeypatch.setattr(ti_module, "_GLIB_SCHEMAS_DIR", schemas_dir)

        schema_src = tmp_path / "gnome-extensions" / "macux-shell@macux.com" / "schemas" / \
                     "org.gnome.shell.extensions.macux.gschema.xml"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            installer = _make_installer(tmp_path)
            paths = installer.compile_gsettings_schema(schema_src)

        # Schema was copied
        assert (schemas_dir / schema_src.name).exists()
        # glib-compile-schemas was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert "glib-compile-schemas" in cmd[0]

    def test_compile_gsettings_schema_missing_raises(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        monkeypatch.setattr(ti_module, "_GLIB_SCHEMAS_DIR", tmp_path / "schemas")

        with pytest.raises(FileNotFoundError):
            _make_installer(tmp_path).compile_gsettings_schema(tmp_path / "nonexistent.xml")

    def test_compile_schemas_failure_raises(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        monkeypatch.setattr(ti_module, "_GLIB_SCHEMAS_DIR", schemas_dir)

        schema_src = tmp_path / "gnome-extensions" / "macux-shell@macux.com" / "schemas" / \
                     "org.gnome.shell.extensions.macux.gschema.xml"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="parse error")
            mock_run.side_effect = subprocess.CalledProcessError(1, "glib-compile-schemas", stderr="parse error")

            with pytest.raises(RuntimeError, match="glib-compile-schemas failed"):
                installer = _make_installer(tmp_path)
                installer.compile_gsettings_schema(schema_src)


class TestThemeInstallerIconCache:
    def test_update_icon_cache_calls_gtk_update(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        icon_dir = tmp_path / "icons" / "MacUX"
        icon_dir.mkdir(parents=True)
        monkeypatch.setattr(ti_module, "_ICON_THEME_DIR", icon_dir)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            installer = _make_installer(tmp_path)
            installer.update_icon_cache(icon_dir)

        cmd = mock_run.call_args.args[0]
        assert "gtk-update-icon-cache" in cmd[0]
        assert str(icon_dir) in cmd

    def test_update_icon_cache_missing_dir_raises(self, tmp_path):
        installer = _make_installer(tmp_path)
        with pytest.raises(FileNotFoundError):
            installer.update_icon_cache(tmp_path / "nonexistent-icons")

    def test_update_icon_cache_failure_raises(self, tmp_path, monkeypatch):
        icon_dir = tmp_path / "icons"
        icon_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="no such icon dir", stdout="")
            with pytest.raises(RuntimeError, match="gtk-update-icon-cache failed"):
                _make_installer(tmp_path).update_icon_cache(icon_dir)


class TestThemeInstallerGnomeSettings:
    def test_apply_gnome_settings_calls_gsettings(self, tmp_path):
        installer = _make_installer(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            installer.apply_gnome_settings()

        # Should have called gsettings at least 4 times (theme, icon, cursor, font)
        assert mock_run.call_count >= 4
        # Flatten all command tokens for a simple "was this key requested" check
        all_tokens = " ".join(
            " ".join(str(t) for t in c.args[0])
            for c in mock_run.call_args_list
        )
        assert "gtk-theme" in all_tokens
        assert "icon-theme" in all_tokens
        assert "cursor-theme" in all_tokens

    def test_apply_gnome_settings_respects_font(self, tmp_path):
        installer = _make_installer(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            installer.apply_gnome_settings(font_family="Inter", font_size=14)

        font_calls = [c.args[0] for c in mock_run.call_args_list
                      if "font-name" in c.args[0]]
        assert any("Inter 14" in " ".join(cmd) for cmd in font_calls)

    def test_apply_gnome_settings_gsettings_missing_raises(self, tmp_path):
        installer = _make_installer(tmp_path)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="gsettings not found"):
                installer.apply_gnome_settings()


class TestThemeInstallerIsInstalled:
    def test_is_installed_false_before_install(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", tmp_path / "not-there" / "gtk-4.0")
        assert _make_installer(tmp_path).is_installed() is False

    def test_is_installed_true_after_creating_dir(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module
        gtk4_dir = tmp_path / "themes" / "MacUX" / "gtk-4.0"
        gtk4_dir.mkdir(parents=True)
        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", gtk4_dir)
        assert _make_installer(tmp_path).is_installed() is True


class TestThemeInstallerFullInstall:
    def test_install_collects_errors_without_raising(self, tmp_path, monkeypatch):
        """Full install should not raise even when individual steps fail."""
        import themes.theme_installer as ti_module

        # Point all target dirs to tmp so they don't touch real FS
        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", tmp_path / "out" / "gtk-4.0")
        monkeypatch.setattr(ti_module, "_GTK4_USER_DIR", tmp_path / "out" / "gtk4-user")
        monkeypatch.setattr(ti_module, "_GTK4_USER_CSS", tmp_path / "out" / "gtk4-user" / "gtk.css")
        monkeypatch.setattr(ti_module, "_ICON_THEME_DIR", tmp_path / "out" / "icons" / "MacUX")
        monkeypatch.setattr(ti_module, "_CURSOR_THEME_DIR", tmp_path / "out" / "icons" / "MacUX-Cursors")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_DIR", tmp_path / "out" / "fontconfig")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_PATH", tmp_path / "out" / "fontconfig" / "90-macux.conf")
        monkeypatch.setattr(ti_module, "_GNOME_SHELL_THEME_DIR", tmp_path / "out" / "gnome-shell")
        monkeypatch.setattr(ti_module, "_GLIB_SCHEMAS_DIR", tmp_path / "out" / "schemas")
        monkeypatch.setattr(ti_module, "_SRC_ICONS", tmp_path / "themes" / "icons" / "MacUX")
        monkeypatch.setattr(ti_module, "_SRC_CURSORS", tmp_path / "themes" / "cursors" / "MacUX")
        monkeypatch.setattr(ti_module, "_SRC_FONTS_CONF", tmp_path / "assets" / "fonts" / "fonts.conf")
        monkeypatch.setattr(ti_module, "_SRC_THEMES", tmp_path / "themes")
        monkeypatch.setattr(ti_module, "_SRC_SCHEMA",
                            tmp_path / "gnome-extensions" / "macux-shell@macux.com" /
                            "schemas" / "org.gnome.shell.extensions.macux.gschema.xml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            installer = _make_installer(tmp_path)
            result = installer.install()

        # Result is an InstallResult (not an exception)
        from themes.theme_installer import InstallResult
        assert isinstance(result, InstallResult)
        # GTK4 theme files should have been created
        assert (tmp_path / "out" / "gtk-4.0" / "gtk.css").exists()

    def test_install_result_has_paths(self, tmp_path, monkeypatch):
        import themes.theme_installer as ti_module

        engine = MagicMock()
        engine.build_full_css.return_value = "/* css */"
        engine.get_gnome_shell_css.return_value = "/* shell */"
        engine._font_config = None

        monkeypatch.setattr(ti_module, "_GTK4_THEME_DIR", tmp_path / "out" / "gtk-4.0")
        monkeypatch.setattr(ti_module, "_GTK4_USER_DIR", tmp_path / "out" / "user-gtk")
        monkeypatch.setattr(ti_module, "_GTK4_USER_CSS", tmp_path / "out" / "user-gtk" / "gtk.css")
        monkeypatch.setattr(ti_module, "_ICON_THEME_DIR", tmp_path / "out" / "MacUX")
        monkeypatch.setattr(ti_module, "_CURSOR_THEME_DIR", tmp_path / "out" / "MacUX-Cursors")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_DIR", tmp_path / "out" / "fc")
        monkeypatch.setattr(ti_module, "_FONTCONFIG_PATH", tmp_path / "out" / "fc" / "90-macux.conf")
        monkeypatch.setattr(ti_module, "_GNOME_SHELL_THEME_DIR", tmp_path / "out" / "gs")
        monkeypatch.setattr(ti_module, "_GLIB_SCHEMAS_DIR", tmp_path / "out" / "schemas")
        monkeypatch.setattr(ti_module, "_SRC_ICONS", tmp_path / "themes" / "icons" / "MacUX")
        monkeypatch.setattr(ti_module, "_SRC_CURSORS", tmp_path / "themes" / "cursors" / "MacUX")
        monkeypatch.setattr(ti_module, "_SRC_FONTS_CONF", tmp_path / "assets" / "fonts" / "fonts.conf")
        monkeypatch.setattr(ti_module, "_SRC_THEMES", tmp_path / "themes")
        monkeypatch.setattr(ti_module, "_SRC_SCHEMA",
                            tmp_path / "gnome-extensions" / "macux-shell@macux.com" /
                            "schemas" / "org.gnome.shell.extensions.macux.gschema.xml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            result = _make_installer(tmp_path, engine=engine).install()

        assert len(result.installed_paths) > 0


# ── ThemeEngine additions (build_full_css / build_component_css) ───────────────

class TestThemeEngineCSSBuilders:
    def test_build_full_css_returns_string(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine()
        css = engine.build_full_css()
        assert isinstance(css, str)
        assert len(css) > 0
        assert "@define-color macux_accent" in css

    def test_build_component_css_returns_string(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine()
        css = engine.build_component_css("dock")
        assert isinstance(css, str)
        assert "@define-color macux_accent" in css

    def test_get_gnome_shell_css_with_explicit_variant(self):
        from themes.theme_engine import ThemeEngine
        engine = ThemeEngine()
        light = engine.get_gnome_shell_css("light")
        dark = engine.get_gnome_shell_css("dark")
        # Both should be strings (content may differ based on template tokens)
        assert isinstance(light, str)
        assert isinstance(dark, str)

    def test_build_full_css_dark_differs_from_light(self):
        from themes.theme_engine import ThemeEngine, ThemeVariant
        light_engine = ThemeEngine()
        light_engine._variant = ThemeVariant.LIGHT
        dark_engine = ThemeEngine()
        dark_engine._variant = ThemeVariant.DARK

        light_css = light_engine.build_full_css()
        dark_css = dark_engine.build_full_css()
        assert light_css != dark_css


# ── macux-ctl argument parser ──────────────────────────────────────────────────

class TestMacuxCtlParser:
    def _parse(self, *args):
        from macuxd.ctl import _build_parser
        return _build_parser().parse_args(list(args))

    def test_status_command(self):
        args = self._parse("status")
        assert args.command == "status"

    def test_theme_install(self):
        args = self._parse("theme", "install")
        assert args.command == "theme"
        assert args.theme_command == "install"

    def test_theme_install_verbose(self):
        args = self._parse("theme", "install", "--verbose")
        assert args.verbose is True

    def test_theme_apply_light(self):
        args = self._parse("theme", "apply", "light")
        assert args.variant == "light"

    def test_theme_apply_dark(self):
        args = self._parse("theme", "apply", "dark")
        assert args.variant == "dark"

    def test_theme_apply_auto(self):
        args = self._parse("theme", "apply", "auto")
        assert args.variant == "auto"

    def test_theme_apply_invalid_rejected(self):
        with pytest.raises(SystemExit):
            self._parse("theme", "apply", "invalid")

    def test_config_get(self):
        args = self._parse("config", "get", "dock.icon_size")
        assert args.command == "config"
        assert args.config_command == "get"
        assert args.key == "dock.icon_size"

    def test_config_set(self):
        args = self._parse("config", "set", "dock.icon_size", "64")
        assert args.key == "dock.icon_size"
        assert args.value == "64"

    def test_restart_component(self):
        args = self._parse("restart", "dock")
        assert args.command == "restart"
        assert args.component == "dock"

    def test_stop_component(self):
        args = self._parse("stop", "spotlight")
        assert args.component == "spotlight"

    def test_start_component(self):
        args = self._parse("start", "launchpad")
        assert args.component == "launchpad"

    def test_theme_uninstall(self):
        args = self._parse("theme", "uninstall")
        assert args.theme_command == "uninstall"

    def test_theme_status(self):
        args = self._parse("theme", "status")
        assert args.theme_command == "status"


# ── GSettings schema validity ──────────────────────────────────────────────────

class TestGSettingsSchema:
    _SCHEMA_PATH = (
        Path(__file__).parent.parent.parent
        / "gnome-extensions"
        / "macux-shell@macux.com"
        / "schemas"
        / "org.gnome.shell.extensions.macux.gschema.xml"
    )

    def test_schema_file_exists(self):
        assert self._SCHEMA_PATH.exists(), f"Schema not found: {self._SCHEMA_PATH}"

    def test_schema_is_valid_xml(self):
        import xml.etree.ElementTree as ET
        tree = ET.parse(self._SCHEMA_PATH)
        root = tree.getroot()
        assert root.tag == "schemalist"

    def test_schema_has_correct_id(self):
        import xml.etree.ElementTree as ET
        tree = ET.parse(self._SCHEMA_PATH)
        root = tree.getroot()
        schema = root.find("schema")
        assert schema is not None
        assert schema.attrib["id"] == "org.gnome.shell.extensions.macux"

    def test_schema_has_keybinding_keys(self):
        import xml.etree.ElementTree as ET
        tree = ET.parse(self._SCHEMA_PATH)
        root = tree.getroot()
        schema = root.find("schema")
        key_names = {k.attrib["name"] for k in schema.findall("key")}
        expected = {
            "macux-spotlight",
            "macux-launchpad",
            "macux-mission-control",
            "macux-notification-center",
            "macux-control-center",
            "macux-show-desktop",
        }
        assert expected.issubset(key_names), f"Missing keys: {expected - key_names}"

    def test_schema_has_theme_key(self):
        import xml.etree.ElementTree as ET
        tree = ET.parse(self._SCHEMA_PATH)
        root = tree.getroot()
        schema = root.find("schema")
        key_names = {k.attrib["name"] for k in schema.findall("key")}
        assert "theme-variant" in key_names
        assert "accent-color" in key_names

    def test_schema_keybinding_types_are_strv(self):
        """All keybinding keys must have type 'as' (string array) for GNOME Shell."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(self._SCHEMA_PATH)
        root = tree.getroot()
        schema = root.find("schema")
        binding_keys = [
            k for k in schema.findall("key")
            if k.attrib["name"].startswith("macux-")
        ]
        for key in binding_keys:
            assert key.attrib["type"] == "as", (
                f"Keybinding {key.attrib['name']!r} must have type='as'"
            )
