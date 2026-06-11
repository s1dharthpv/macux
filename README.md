# MacUX

**macOS-inspired desktop environment layer for Ubuntu 24.04**

MacUX delivers a polished macOS-like workflow on GNOME Shell without replacing Ubuntu's core desktop. It runs as a set of overlapping GTK4 applications and GNOME Shell extensions, fully reversible at any time.

---

## Components

| Component | Status | Description |
|---|---|---|
| **Dock** | Phase 4 | Bottom-centered dock, magnification, auto-hide, drag-and-drop |
| **Spotlight** | Phase 5 | Super+Space universal search — apps, files, calculator, web |
| **Launchpad** | Phase 6 | Fullscreen app launcher with folder grouping |
| **Menu Bar** | Phase 7 | Global menu bar with app menus, clock, status indicators |
| **Control Center** | Phase 8 | Quick controls: WiFi, Bluetooth, Volume, Brightness |
| **Notification Center** | Phase 9 | Notification history, calendar, widgets |
| **Mission Control** | Phase 10 | Window and workspace overview (Super+Up) |
| **Finder** | Phase 11 | Full-featured file manager with sidebar, tags, preview |

---

## Requirements

- Ubuntu 24.04 LTS
- GNOME Shell 46
- GTK4 4.14+
- Libadwaita 1.5+
- Python 3.12+
- Wayland or X11

---

## Installation

```bash
git clone https://github.com/macux/macux.git
cd macux
bash installer/install.sh
```

For development installation (editable):

```bash
bash installer/install.sh --dev
```

---

## Post-install

1. Log out and back in (required for the GNOME Shell extension)
2. MacUX starts automatically via systemd user service
3. Configure at `~/.config/macux/config.toml`

---

## Configuration

```toml
# ~/.config/macux/config.toml
[global]
theme = "auto"          # light | dark | auto
accent_color = "#0071e3"

[dock]
icon_size = 48
magnification = true
auto_hide = false

[spotlight]
hotkey = "<Super>space"
```

Full reference: `config/config.toml.default`

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Super + Space` | Spotlight Search |
| `F4` | Launchpad |
| `Super + Up` | Mission Control |
| `Super + N` | Notification Center |
| `Super + Shift + C` | Control Center |
| `Super + D` | Show Desktop |

---

## Daemon control

```bash
# Status
systemctl --user status macux.service

# Logs
journalctl --user -u macux.service -f

# Restart
systemctl --user restart macux.service

# Stop
systemctl --user stop macux.service
```

---

## Uninstall

```bash
bash installer/uninstall.sh          # keeps config/data
bash installer/uninstall.sh --purge  # removes everything
```

---

## Development

```bash
pip3.12 install -e ".[dev]"
pytest                        # run all tests
ruff check .                  # lint
mypy macuxd/                  # type-check
```

---

## Architecture

See `docs/PHASE1_ARCHITECTURE.md` for the full technical design document including:
- Component architecture diagrams
- DBus API contracts
- SQLite database schemas
- Event bus design
- Security model
- Performance targets

---

## License

GPL-3.0-or-later — see LICENSE file.
