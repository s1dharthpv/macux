"""MacUX version constants and helpers."""

from __future__ import annotations

VERSION: tuple[int, int, int] = (1, 0, 0)
VERSION_STRING: str = "1.0.0"
RELEASE_NAME: str = "noble"       # Ubuntu 24.04 codename
DEB_REVISION: str = "1"
DEB_VERSION: str = f"{VERSION_STRING}-{DEB_REVISION}"
MIN_GNOME_SHELL: int = 46
MIN_PYTHON: tuple[int, int] = (3, 12)


def version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse ``"1.2.3"`` → ``(1, 2, 3)``.

    Raises ``ValueError`` if any component is not an integer.
    """
    parts = version_str.strip().split(".")
    if not parts or parts == [""]:
        raise ValueError(f"Invalid version string: {version_str!r}")
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"Invalid version string: {version_str!r}") from exc


def version_string(tup: tuple[int, ...]) -> str:
    """``(1, 2, 3)`` → ``"1.2.3"``."""
    if not tup:
        raise ValueError("Version tuple must not be empty")
    return ".".join(str(n) for n in tup)


def is_newer(a: str, b: str) -> bool:
    """Return ``True`` if version *a* is strictly newer than *b*."""
    return version_tuple(a) > version_tuple(b)


def is_compatible(installed: str, required: str) -> bool:
    """Return ``True`` if *installed* satisfies *required* (same major, >=minor)."""
    iv = version_tuple(installed)
    rv = version_tuple(required)
    if not iv or not rv:
        return False
    return iv[0] == rv[0] and iv >= rv
