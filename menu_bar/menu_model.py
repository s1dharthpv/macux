"""MacUX Menu Bar — dbusmenu menu model.

MenuItem is a pure dataclass representing a node in the application menu tree.
parse_layout() converts a raw dbusmenu GetLayout response into a MenuItem tree.
visible_items() filters the root's children down to what should be rendered.

dbusmenu protocol
-----------------
GetLayout(parentId=0, recursionDepth=-1, propertyNames=[])
  → (revision: int, layout: (id, {str: variant}, [children...]))

Each child is a GLib.Variant wrapping another (id, props, children) tuple.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MenuItem:
    """One node in a dbusmenu menu tree."""

    item_id: int
    label: str
    is_separator: bool = False
    enabled: bool = True
    visible: bool = True
    icon_name: str = ""
    toggle_type: str = ""    # "" | "checkmark" | "radio"
    toggle_state: int = -1   # -1=unknown, 0=off, 1=on
    children: list[MenuItem] = field(default_factory=list)

    @property
    def is_submenu(self) -> bool:
        return bool(self.children)

    @property
    def display_label(self) -> str:
        """Strip GTK mnemonic underscores: '_File' → 'File'."""
        return self.label.replace("_", "")


def _unpack(value):
    """Unwrap a GLib.Variant if present; return the value otherwise."""
    if value is None:
        return None
    if hasattr(value, "unpack"):
        v = value.unpack()
        # Byte arrays become Python bytes objects
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="replace")
        return v
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _prop(props: dict, key: str, default):
    raw = props.get(key)
    if raw is None:
        return default
    val = _unpack(raw)
    return val if val is not None else default


def parse_layout(layout_tuple) -> MenuItem:
    """
    Recursively parse a dbusmenu layout tuple into a MenuItem tree.

    Args:
        layout_tuple: A 3-tuple ``(id, props_dict, children_list)``.
                      May contain raw Python values or GLib.Variant wrappers.

    Returns:
        The root MenuItem (id=0), whose children are the top-level menu items.
    """
    item_id, props, children = layout_tuple

    label       = str(_prop(props, "label", ""))
    is_sep      = _prop(props, "type", "") == "separator"
    enabled     = bool(_prop(props, "enabled", True))
    visible     = bool(_prop(props, "visible", True))
    icon_name   = str(_prop(props, "icon-name", ""))
    toggle_type = str(_prop(props, "toggle-type", ""))
    toggle_st   = int(_prop(props, "toggle-state", -1))

    parsed_children: list[MenuItem] = []
    for child in children:
        child_tuple = child.unpack() if hasattr(child, "unpack") else child
        parsed_children.append(parse_layout(child_tuple))

    return MenuItem(
        item_id=int(item_id),
        label=label,
        is_separator=bool(is_sep),
        enabled=enabled,
        visible=visible,
        icon_name=icon_name,
        toggle_type=toggle_type,
        toggle_state=toggle_st,
        children=parsed_children,
    )


def visible_items(menu: MenuItem) -> list[MenuItem]:
    """Return visible, non-hidden direct children of *menu* (the root node)."""
    return [c for c in menu.children if c.visible]
