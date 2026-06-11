"""MacUX Launchpad — app filtering logic.

Pure function: no GTK, fully testable.
"""

from __future__ import annotations


def filter_apps(registry: dict, query: str) -> set[str]:
    """
    Return desktop IDs whose app matches *query*.

    Matching is case-insensitive and checks:
      1. App name contains query
      2. exec_base starts with query
      3. Category contains query

    Args:
        registry: Mapping of desktop_id → AppInfo (from dock.desktop_file).
        query:    Search string from the Launchpad search entry.

    Returns:
        Set of matching desktop IDs.  Empty query → all non-nodisplay apps.
    """
    q = query.strip().lower()

    result: set[str] = set()
    for desktop_id, info in registry.items():
        if info.nodisplay:
            continue
        if not q:
            result.add(desktop_id)
            continue
        if q in info.name.lower():
            result.add(desktop_id)
        elif info.exec_base and info.exec_base.lower().startswith(q):
            result.add(desktop_id)
        elif any(q in c.lower() for c in info.categories):
            result.add(desktop_id)

    return result
