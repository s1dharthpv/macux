"""GSettings schema compilation helpers."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)

COMPILE_TOOL = "glib-compile-schemas"


def find_compile_tool() -> str | None:
    """Return the absolute path to ``glib-compile-schemas``, or ``None``."""
    return shutil.which(COMPILE_TOOL)


def compile_schemas(schema_dir: Path, strict: bool = False) -> bool:
    """Compile all ``.gschema.xml`` files in *schema_dir*.

    Returns ``True`` on success.  If *strict* is ``True`` and the tool is not
    found, raises ``RuntimeError`` instead of returning ``False``.
    """
    tool = find_compile_tool()
    if tool is None:
        if strict:
            raise RuntimeError(f"{COMPILE_TOOL} not found in PATH")
        _log.warning("%s not found — skipping schema compilation", COMPILE_TOOL)
        return False

    if not schema_dir.is_dir():
        raise ValueError(f"Schema directory does not exist: {schema_dir}")

    try:
        result = subprocess.run(
            [tool, str(schema_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            _log.error("Schema compilation failed: %s", result.stderr.strip())
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        _log.error("Schema compilation timed out")
        return False
    except OSError as exc:
        _log.error("Schema compilation error: %s", exc)
        return False


def list_schemas(schema_dir: Path) -> list[Path]:
    """Return sorted list of ``.gschema.xml`` files in *schema_dir*."""
    if not schema_dir.is_dir():
        return []
    return sorted(schema_dir.glob("*.gschema.xml"))


def validate_schema_dir(schema_dir: Path) -> list[str]:
    """Return a list of problems with *schema_dir* (empty list = OK)."""
    errors: list[str] = []
    if not schema_dir.exists():
        errors.append(f"Schema directory does not exist: {schema_dir}")
        return errors
    if not schema_dir.is_dir():
        errors.append(f"Not a directory: {schema_dir}")
        return errors
    schemas = list_schemas(schema_dir)
    if not schemas:
        errors.append(f"No .gschema.xml files found in {schema_dir}")
    return errors


def schema_ids_from_file(schema_file: Path) -> list[str]:
    """Extract ``id=`` attribute values from a schema XML file.

    Returns a list of schema ID strings (e.g.
    ``["org.gnome.shell.extensions.macux-mission-control"]``).
    Does not parse full XML — uses simple line scanning.
    """
    ids: list[str] = []
    try:
        text = schema_file.read_text(encoding="utf-8")
    except OSError:
        return ids
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("<schema") and 'id="' in line:
            start = line.index('id="') + 4
            end = line.index('"', start)
            ids.append(line[start:end])
    return ids
