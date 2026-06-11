"""MacUX Theme Installer — installs theme assets to the user's local directories.

Handles:
  - GTK4 CSS → ~/.local/share/themes/MacUX/gtk-4.0/gtk.css
                 ~/.config/gtk-4.0/gtk.css  (direct user override)
  - Icon theme → ~/.local/share/icons/MacUX/
  - Cursor theme → ~/.local/share/icons/MacUX-Cursors/
  - Fontconfig → ~/.config/fontconfig/conf.d/90-macux.conf
  - GNOME Shell CSS → ~/.local/share/themes/MacUX/gnome-shell/gnome-shell.css
  - GSettings schema → ~/.local/share/glib-2.0/schemas/
  - GNOME appearance settings via gsettings subprocess
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from themes.theme_engine import ThemeEngine

logger = logging.getLogger(__name__)

# Source tree roots (relative to this file's parent)
_SRC_ROOT = Path(__file__).parent.parent
_SRC_THEMES = Path(__file__).parent
_SRC_ICONS = _SRC_THEMES / "icons" / "MacUX"
_SRC_CURSORS = _SRC_THEMES / "cursors" / "MacUX"
_SRC_FONTS_CONF = _SRC_ROOT / "assets" / "fonts" / "fonts.conf"
_SRC_SCHEMA = (
    _SRC_ROOT
    / "gnome-extensions"
    / "macux-shell@macux.com"
    / "schemas"
    / "org.gnome.shell.extensions.macux.gschema.xml"
)

# Target directories
_THEMES_DIR = Path("~/.local/share/themes").expanduser()
_ICONS_DIR = Path("~/.local/share/icons").expanduser()
_GTK4_USER_DIR = Path("~/.config/gtk-4.0").expanduser()
_FONTCONFIG_DIR = Path("~/.config/fontconfig/conf.d").expanduser()
_GLIB_SCHEMAS_DIR = Path("~/.local/share/glib-2.0/schemas").expanduser()

# Named targets
_GTK_THEME_DIR = _THEMES_DIR / "MacUX"
_GNOME_SHELL_THEME_DIR = _GTK_THEME_DIR / "gnome-shell"
_GTK4_THEME_DIR = _GTK_THEME_DIR / "gtk-4.0"
_ICON_THEME_DIR = _ICONS_DIR / "MacUX"
_CURSOR_THEME_DIR = _ICONS_DIR / "MacUX-Cursors"
_FONTCONFIG_PATH = _FONTCONFIG_DIR / "90-macux.conf"
_GTK4_USER_CSS = _GTK4_USER_DIR / "gtk.css"


@dataclass
class InstallResult:
    """Result of a theme installation operation."""

    success: bool
    installed_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_path(self, path: Path) -> None:
        self.installed_paths.append(path)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.success = False


class ThemeInstaller:
    """
    Installs MacUX theme assets to the user's XDG directories.

    Usage::

        installer = ThemeInstaller(theme_engine=engine)
        result = installer.install()
        if not result.success:
            for err in result.errors:
                print(err)
    """

    def __init__(
        self,
        source_dir: Path | None = None,
        theme_engine: ThemeEngine | None = None,
    ) -> None:
        self._src = source_dir or _SRC_ROOT
        self._engine = theme_engine

    # ── Public API ────────────────────────────────────────────────────────────

    def install(self) -> InstallResult:
        """
        Perform a full theme installation.

        Steps (all non-fatal — errors are collected, not raised):
          1. Install GTK4 theme CSS
          2. Install icon theme
          3. Install cursor theme index
          4. Install fontconfig
          5. Install GNOME Shell CSS
          6. Compile GSettings schema
          7. Update icon cache
          8. Apply GNOME desktop settings
        """
        result = InstallResult(success=True)
        logger.info("Starting MacUX theme installation...")

        steps = [
            ("GTK4 theme", self._step_gtk_theme),
            ("icon theme", self._step_icon_theme),
            ("cursor theme", self._step_cursor_theme),
            ("fontconfig", self._step_fontconfig),
            ("GNOME Shell CSS", self._step_gnome_shell_css),
            ("GSettings schema", self._step_gsettings_schema),
            ("icon cache", self._step_icon_cache),
            ("GNOME settings", self._step_gnome_settings),
        ]

        for label, step in steps:
            try:
                paths = step()
                if paths:
                    result.installed_paths.extend(paths)
                logger.info("  ✓ %s", label)
            except Exception as exc:
                msg = f"{label}: {exc}"
                result.add_error(msg)
                logger.warning("  ✗ %s", msg)

        if result.success:
            logger.info("MacUX theme installation complete (%d paths).", len(result.installed_paths))
        else:
            logger.warning("Installation finished with %d error(s).", len(result.errors))

        return result

    def uninstall(self) -> None:
        """Remove all installed MacUX theme files."""
        targets = [
            _GTK_THEME_DIR,
            _ICON_THEME_DIR,
            _CURSOR_THEME_DIR,
            _FONTCONFIG_PATH,
            _GTK4_USER_CSS,
            _GLIB_SCHEMAS_DIR / _SRC_SCHEMA.name,
        ]
        for path in targets:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
                logger.info("Removed: %s", path)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Removed directory: %s", path)

        # Recompile schemas after removing ours
        self._compile_schemas_dir(_GLIB_SCHEMAS_DIR)

        logger.info("MacUX theme uninstalled.")

    def is_installed(self) -> bool:
        """Return True if the MacUX GTK4 theme directory exists."""
        return _GTK4_THEME_DIR.is_dir()

    def update(self) -> InstallResult:
        """Re-run install, regenerating CSS from the current engine state."""
        return self.install()

    # ── GTK4 theme ────────────────────────────────────────────────────────────

    def install_gtk_theme(self) -> list[Path]:
        """
        Write generated GTK4 CSS to:
          - ~/.local/share/themes/MacUX/gtk-4.0/gtk.css  (for theme switcher)
          - ~/.config/gtk-4.0/gtk.css                     (applied immediately)
        """
        css = self._get_full_css()
        paths: list[Path] = []

        # Theme-named location
        _GTK4_THEME_DIR.mkdir(parents=True, exist_ok=True)
        named_path = _GTK4_THEME_DIR / "gtk.css"
        named_path.write_text(css, encoding="utf-8")
        paths.append(named_path)

        # User-level override (applied to every GTK4 app, no theme switch needed)
        _GTK4_USER_DIR.mkdir(parents=True, exist_ok=True)
        _GTK4_USER_CSS.write_text(css, encoding="utf-8")
        paths.append(_GTK4_USER_CSS)

        return paths

    # ── Icon theme ────────────────────────────────────────────────────────────

    def install_icon_theme(self) -> list[Path]:
        """
        Copy icon theme from source tree to ~/.local/share/icons/MacUX/.
        Uses a recursive copy so individual SVGs are preserved.
        """
        src = self._resolve_path(_SRC_ICONS)
        if not src.exists():
            raise FileNotFoundError(f"Icon source not found: {src}")

        if _ICON_THEME_DIR.exists():
            shutil.rmtree(_ICON_THEME_DIR)

        shutil.copytree(src, _ICON_THEME_DIR, dirs_exist_ok=False)
        return [_ICON_THEME_DIR]

    # ── Cursor theme ──────────────────────────────────────────────────────────

    def install_cursor_theme(self) -> list[Path]:
        """
        Copy cursor theme index to ~/.local/share/icons/MacUX-Cursors/.

        The cursor theme declares Inherits=Bibata-Modern-Classic,Adwaita,default
        so actual cursor images come from those upstream themes.
        """
        src = self._resolve_path(_SRC_CURSORS)
        if not src.exists():
            raise FileNotFoundError(f"Cursor source not found: {src}")

        _CURSOR_THEME_DIR.mkdir(parents=True, exist_ok=True)
        dest = _CURSOR_THEME_DIR / "index.theme"
        shutil.copy2(src / "index.theme", dest)
        return [dest]

    # ── Fontconfig ────────────────────────────────────────────────────────────

    def install_fontconfig(self) -> list[Path]:
        """
        Copy the MacUX fontconfig XML to ~/.config/fontconfig/conf.d/90-macux.conf.
        This configures SF Pro Display as the default sans-serif on the system.
        """
        src = self._resolve_path(_SRC_FONTS_CONF)
        if not src.exists():
            raise FileNotFoundError(f"Fontconfig source not found: {src}")

        _FONTCONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, _FONTCONFIG_PATH)
        return [_FONTCONFIG_PATH]

    # ── GNOME Shell CSS ───────────────────────────────────────────────────────

    def install_gnome_shell_theme(self) -> list[Path]:
        """
        Write the generated GNOME Shell CSS (both variants) to the theme directory.
        The extension's CSSGenerator reads these files at runtime to substitute tokens.
        """
        _GNOME_SHELL_THEME_DIR.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []

        if self._engine is not None:
            for variant in ("light", "dark"):
                css = self._engine.get_gnome_shell_css(variant)
                dest = _GNOME_SHELL_THEME_DIR / f"gnome-shell-{variant}.css"
                dest.write_text(css, encoding="utf-8")
                paths.append(dest)
        else:
            # Copy source templates when no engine is wired
            src_dir = self._resolve_path(_SRC_THEMES / "gnome-shell")
            for src_file in src_dir.glob("gnome-shell-*.css"):
                dest = _GNOME_SHELL_THEME_DIR / src_file.name
                shutil.copy2(src_file, dest)
                paths.append(dest)

        # Write the primary gnome-shell.css that GNOME Shell loads by name
        if paths:
            primary = _GNOME_SHELL_THEME_DIR / "gnome-shell.css"
            # Point to the light variant; extension replaces at runtime
            shutil.copy2(paths[0], primary)
            paths.append(primary)

        return paths

    # ── GSettings schema ──────────────────────────────────────────────────────

    def compile_gsettings_schema(self, schema_src: Path | None = None) -> list[Path]:
        """
        Copy .gschema.xml to the user schemas directory and compile it.

        Returns the path to the compiled schema file.
        """
        src = schema_src or self._resolve_path(_SRC_SCHEMA)
        if not src.exists():
            raise FileNotFoundError(f"Schema source not found: {src}")

        _GLIB_SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
        dest = _GLIB_SCHEMAS_DIR / src.name
        shutil.copy2(src, dest)

        self._compile_schemas_dir(_GLIB_SCHEMAS_DIR)
        return [dest]

    # ── Icon cache ────────────────────────────────────────────────────────────

    def update_icon_cache(self, icon_dir: Path | None = None) -> list[Path]:
        """Run gtk-update-icon-cache on the MacUX icon theme directory."""
        target = icon_dir or _ICON_THEME_DIR
        if not target.exists():
            raise FileNotFoundError(f"Icon directory not found: {target}")

        result = subprocess.run(
            ["gtk-update-icon-cache", "--force", "--quiet", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gtk-update-icon-cache failed: {result.stderr.strip()}"
            )

        cache = target / "icon-theme.cache"
        return [cache] if cache.exists() else []

    # ── GNOME appearance settings ─────────────────────────────────────────────

    def apply_gnome_settings(self, font_family: str = "SF Pro Text", font_size: int = 13) -> list[Path]:
        """
        Apply GTK theme, icon theme, cursor theme, and font via gsettings.

        These settings persist across reboots in the user's dconf database.
        """
        settings: list[tuple[str, str, str]] = [
            ("org.gnome.desktop.interface", "gtk-theme", "MacUX"),
            ("org.gnome.desktop.interface", "icon-theme", "MacUX"),
            ("org.gnome.desktop.interface", "cursor-theme", "MacUX-Cursors"),
            ("org.gnome.desktop.interface", "font-name", f"{font_family} {font_size}"),
            (
                "org.gnome.desktop.wm.preferences",
                "titlebar-font",
                f"SF Pro Display Bold {font_size}",
            ),
            # Disable the default GNOME Shell panel (replaced by MacUX menu bar)
            ("org.gnome.desktop.interface", "enable-animations", "true"),
        ]

        errors: list[str] = []
        for schema, key, value in settings:
            try:
                subprocess.run(
                    ["gsettings", "set", schema, key, value],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logger.debug("gsettings set %s %s = %s", schema, key, value)
            except subprocess.CalledProcessError as exc:
                msg = f"gsettings set {schema} {key}: {exc.stderr.strip()}"
                errors.append(msg)
                logger.warning(msg)
            except FileNotFoundError:
                raise RuntimeError("gsettings not found — is GNOME installed?")

        if errors:
            raise RuntimeError(
                f"Some gsettings calls failed ({len(errors)}): {errors[0]}"
            )

        return []  # gsettings writes to dconf, no file paths to report

    # ── Private helpers ───────────────────────────────────────────────────────

    def _step_gtk_theme(self) -> list[Path]:
        return self.install_gtk_theme()

    def _step_icon_theme(self) -> list[Path]:
        return self.install_icon_theme()

    def _step_cursor_theme(self) -> list[Path]:
        return self.install_cursor_theme()

    def _step_fontconfig(self) -> list[Path]:
        return self.install_fontconfig()

    def _step_gnome_shell_css(self) -> list[Path]:
        return self.install_gnome_shell_theme()

    def _step_gsettings_schema(self) -> list[Path]:
        return self.compile_gsettings_schema()

    def _step_icon_cache(self) -> list[Path]:
        return self.update_icon_cache()

    def _step_gnome_settings(self) -> list[Path]:
        if self._engine is not None:
            font_cfg = getattr(self._engine, "_font_config", None)
            family = font_cfg.ui_family if font_cfg else "SF Pro Text"
            size = int(font_cfg.ui_size) if font_cfg else 13
        else:
            family, size = "SF Pro Text", 13
        return self.apply_gnome_settings(family, size)

    def _get_full_css(self) -> str:
        if self._engine is not None:
            return self._engine.build_full_css()
        # Fallback: read pre-built CSS from source tree if no engine
        base_css = self._resolve_path(_SRC_THEMES / "gtk4" / "base.css")
        return base_css.read_text(encoding="utf-8") if base_css.exists() else ""

    def _resolve_path(self, path: Path) -> Path:
        """Resolve a source path relative to the installer's source root if needed."""
        if path.is_absolute():
            return path
        return self._src / path

    @staticmethod
    def _compile_schemas_dir(schemas_dir: Path) -> None:
        """Run glib-compile-schemas on the given directory."""
        try:
            subprocess.run(
                ["glib-compile-schemas", str(schemas_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.debug("glib-compile-schemas succeeded for %s", schemas_dir)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"glib-compile-schemas failed: {exc.stderr.strip()}"
            ) from exc
        except FileNotFoundError:
            raise RuntimeError(
                "glib-compile-schemas not found. Install: sudo apt install libglib2.0-bin"
            )
