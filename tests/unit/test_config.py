"""Unit tests for macuxd.config — ConfigManager."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary directory for config files."""
    return tmp_path


@pytest.fixture
def defaults_toml(tmp_path):
    content = """
[global]
theme = "light"
accent_color = "#0071e3"
font_size = 13
animations = true

[dock]
icon_size = 48
magnification = true
auto_hide = false

[spotlight]
max_results = 12
search_web = true
"""
    path = tmp_path / "config.toml.default"
    path.write_text(content)
    return path


@pytest.fixture
def user_toml(tmp_path):
    content = """
[global]
theme = "dark"

[dock]
icon_size = 56
"""
    path = tmp_path / "config.toml"
    path.write_text(content)
    return path


def make_config(defaults_path: Path, user_path: Path | None = None):
    """Import and configure ConfigManager with patched paths."""
    import macuxd.config as cfg_module
    original_defaults = cfg_module._DEFAULTS_PATH
    original_user = cfg_module._USER_CONFIG_PATH
    original_dir = cfg_module._USER_CONFIG_DIR

    cfg_module._DEFAULTS_PATH = defaults_path
    cfg_module._USER_CONFIG_PATH = user_path or Path("/nonexistent/config.toml")
    cfg_module._USER_CONFIG_DIR = user_path.parent if user_path else Path("/nonexistent")

    from macuxd.config import ConfigManager
    manager = ConfigManager()
    manager.load()

    # Restore
    cfg_module._DEFAULTS_PATH = original_defaults
    cfg_module._USER_CONFIG_PATH = original_user
    cfg_module._USER_CONFIG_DIR = original_dir

    return manager


class TestConfigLoad:
    def test_loads_defaults_only(self, defaults_toml):
        mgr = make_config(defaults_toml)
        assert mgr.get("global.theme") == "light"
        assert mgr.get("dock.icon_size") == 48

    def test_user_overrides_defaults(self, defaults_toml, user_toml):
        mgr = make_config(defaults_toml, user_toml)
        assert mgr.get("global.theme") == "dark"      # user override
        assert mgr.get("dock.icon_size") == 56         # user override
        assert mgr.get("global.font_size") == 13       # kept from defaults
        assert mgr.get("dock.auto_hide") is False       # kept from defaults

    def test_missing_key_returns_default(self, defaults_toml):
        mgr = make_config(defaults_toml)
        assert mgr.get("nonexistent.key", "fallback") == "fallback"
        assert mgr.get("nonexistent.key") is None

    def test_nested_dot_access(self, defaults_toml):
        mgr = make_config(defaults_toml)
        assert mgr.get("dock.magnification") is True
        assert mgr.get("spotlight.max_results") == 12


class TestConfigSet:
    def test_set_fires_callback(self, defaults_toml, tmp_path):
        user_path = tmp_path / "config.toml"
        mgr = make_config(defaults_toml, user_path)

        changes: list[tuple] = []
        mgr.on_change(lambda k, v: changes.append((k, v)))

        mgr.set("global.theme", "dark")
        assert len(changes) == 1
        assert changes[0] == ("global.theme", "dark")

    def test_set_persists_value(self, defaults_toml, tmp_path):
        user_path = tmp_path / "config.toml"
        mgr = make_config(defaults_toml, user_path)
        mgr.set("dock.icon_size", 64)
        assert mgr.get("dock.icon_size") == 64

    def test_reset_reverts_to_default(self, defaults_toml, tmp_path):
        user_path = tmp_path / "config.toml"
        mgr = make_config(defaults_toml, user_path)
        mgr.set("dock.icon_size", 64)
        mgr.reset("dock.icon_size")
        assert mgr.get("dock.icon_size") == 48


class TestDeepMerge:
    def test_merge_basic(self):
        from macuxd.config import _deep_merge
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 99, "e": 4}}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": {"c": 99, "d": 3, "e": 4}}

    def test_merge_does_not_mutate_base(self):
        from macuxd.config import _deep_merge
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        _deep_merge(base, override)
        assert "c" not in base["a"]

    def test_merge_scalar_override(self):
        from macuxd.config import _deep_merge
        base = {"a": {"b": 1}}
        override = {"a": 99}      # scalar overrides dict
        result = _deep_merge(base, override)
        assert result["a"] == 99
