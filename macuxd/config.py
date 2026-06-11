"""MacUX configuration loader, validator, and live-watcher."""

from __future__ import annotations

import logging
import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent.parent / "config" / "config.toml.default"
_USER_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "macux"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, recursing into nested dicts."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    """
    Loads, merges, and watches the MacUX configuration.

    Priority (lowest → highest):
      1. Shipped defaults (config/config.toml.default)
      2. User config (~/.config/macux/config.toml)
    """

    def __init__(self) -> None:
        self._defaults: dict[str, Any] = {}
        self._user: dict[str, Any] = {}
        self._merged: dict[str, Any] = {}
        self._change_callbacks: list[Callable[[str, Any], None]] = []
        self._observer: Observer | None = None

    def load(self) -> None:
        self._defaults = _load_toml(_DEFAULTS_PATH)
        self._user = _load_toml(_USER_CONFIG_PATH)
        self._merge()
        logger.info("Configuration loaded. User config: %s", _USER_CONFIG_PATH)

    def _merge(self) -> None:
        self._merged = _deep_merge(self._defaults, self._user)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value using dot-notation key, e.g. 'dock.icon_size'.
        Returns default if the key does not exist.
        """
        parts = key.split(".")
        node: Any = self._merged
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the user config layer and persist to disk.
        Creates the user config file if it does not exist.
        """
        parts = key.split(".")
        node = self._user
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self._merge()
        self._persist_user_config()
        for cb in self._change_callbacks:
            try:
                cb(key, value)
            except Exception:
                logger.exception("Config change callback raised for key %r", key)

    def reset(self, key: str) -> None:
        """Remove a key from the user config, reverting to default."""
        parts = key.split(".")
        node = self._user
        for part in parts[:-1]:
            if part not in node:
                return
            node = node[part]
        node.pop(parts[-1], None)
        self._merge()
        self._persist_user_config()
        default_val = self.get(key)
        for cb in self._change_callbacks:
            try:
                cb(key, default_val)
            except Exception:
                logger.exception("Config reset callback raised for key %r", key)

    def _persist_user_config(self) -> None:
        _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # tomllib is read-only; use tomli_w if available, else manual serialization
        try:
            import tomli_w
            with open(_USER_CONFIG_PATH, "wb") as f:
                tomli_w.dump(self._user, f)
        except ImportError:
            # Fallback: write a basic TOML manually for simple flat/nested dicts
            with open(_USER_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(_dict_to_toml(self._user))
        logger.debug("User config persisted to %s", _USER_CONFIG_PATH)

    def on_change(self, callback: Callable[[str, Any], None]) -> None:
        self._change_callbacks.append(callback)

    def start_watching(self) -> None:
        """Watch the user config file for external changes and reload."""
        class _Handler(FileSystemEventHandler):
            def __init__(self_, manager: ConfigManager) -> None:
                self_._manager = manager

            def on_modified(self_, event: FileModifiedEvent) -> None:
                if Path(event.src_path) == _USER_CONFIG_PATH:
                    logger.info("Config file changed externally, reloading.")
                    old = deepcopy(self_._manager._merged)
                    self_._manager._user = _load_toml(_USER_CONFIG_PATH)
                    self_._manager._merge()
                    # Fire callbacks for changed keys (flat scan)
                    _notify_diff(old, self_._manager._merged, "", self_._manager._change_callbacks)

        _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(_USER_CONFIG_DIR), recursive=False)
        self._observer.start()
        logger.debug("Config file watcher started on %s", _USER_CONFIG_DIR)

    def stop_watching(self) -> None:
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.debug("Config file watcher stopped.")

    @property
    def all(self) -> dict[str, Any]:
        return deepcopy(self._merged)


def _notify_diff(
    old: dict,
    new: dict,
    prefix: str,
    callbacks: list[Callable[[str, Any], None]],
) -> None:
    all_keys = set(old) | set(new)
    for key in all_keys:
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        old_val = old.get(key)
        new_val = new.get(key)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            _notify_diff(old_val, new_val, full_key, callbacks)
        elif old_val != new_val:
            for cb in callbacks:
                try:
                    cb(full_key, new_val)
                except Exception:
                    logger.exception("Diff callback raised for key %r", full_key)


def _dict_to_toml(data: dict, indent: int = 0) -> str:
    """Minimal TOML serializer for simple nested dicts (fallback for tomli_w)."""
    lines: list[str] = []
    tables: list[tuple[str, dict]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        elif isinstance(value, list):
            items = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
            lines.append(f"{key} = [{items}]")
    result = "\n".join(lines)
    for table_key, table_val in tables:
        result += f"\n\n[{table_key}]\n" + _dict_to_toml(table_val)
    return result
