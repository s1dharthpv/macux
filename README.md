<div align="center">

# MacUX

**macOS-inspired desktop environment layer for Ubuntu 24.04**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![GNOME Shell](https://img.shields.io/badge/GNOME_Shell-46-4A86CF?logo=gnome&logoColor=white)](https://www.gnome.org)
[![GTK](https://img.shields.io/badge/GTK-4.14-7B3FBE?logo=gtk&logoColor=white)](https://gtk.org)
[![Tests](https://img.shields.io/badge/Tests-1212_passing-brightgreen)](tests/)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04_LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)

MacUX brings the macOS workflow to GNOME Shell — global menu bar, Spotlight search, Dock with magnification, Launchpad, Mission Control, Finder, and more. It runs entirely on top of your existing Ubuntu install and is **fully reversible** at any time.

</div>

---

## Screenshots

> Running on Ubuntu 24.04 LTS · GNOME Shell 46 · X11

### Menu Bar + Dock
```
┌─────────────────────────────────────────────────────────────────────┐
│  Finder  File  Edit  View  Go  Window  Help        Wed 11 Jun 14:32 │  ← Global Menu Bar
└─────────────────────────────────────────────────────────────────────┘

  ╔═══════════════════════════════════════════════════════════════════╗
  ║                      Desktop / Wallpaper                          ║
  ╚═══════════════════════════════════════════════════════════════════╝

        ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐
        │  │ │  │ │  │ │  │ │  │ │  │ │  │ │  │ │  │   ← Dock
        └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘
```

### Spotlight Search (`Super + Space`)
```
          ╔══════════════════════════════════╗
          ║  🔍  Search apps, files, web...  ║
          ╠══════════════════════════════════╣
          ║  📁  Documents                   ║
          ║  🖥  System Preferences          ║
          ║  📝  Text Editor                 ║
          ║  🔢  Calculator: 2 + 2 = 4       ║
          ╚══════════════════════════════════╝
```

### Launchpad (`F4`)
```
  ┌──────────────────────────────────────────────────────────────┐
  │  🔍 Search apps...                                           │
  │                                                              │
  │   ╔══╗  ╔══╗  ╔══╗  ╔══╗  ╔══╗  ╔══╗                       │
  │   ║  ║  ║  ║  ║  ║  ║  ║  ║  ║  ║  ║   ← Paginated grid   │
  │   ╚══╝  ╚══╝  ╚══╝  ╚══╝  ╚══╝  ╚══╝                       │
  │  Files  Code  Term  Music  Mail  Calc                        │
  │                                                              │
  │                    ● ○ ○                                     │
  └──────────────────────────────────────────────────────────────┘
```

### Mission Control (`Super + Up`)
```
  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │ Terminal   │  │  Browser   │  │   Editor   │   ← All windows tiled
  │            │  │            │  │            │
  └────────────┘  └────────────┘  └────────────┘
  [ Workspace 1 ]  [ Workspace 2 ]  [ + ]
```

### Finder
```
  ┌─────────────────────────────────────────────────────────────┐
  │  ← →   📁 Home / Documents                    ☰  ⊞        │
  ├────────────┬────────────────────────────────────────────────┤
  │ Favourites │  📁 Projects    📁 Notes    📄 report.pdf     │
  │  Home      │  📁 Downloads   📁 Desktop  📝 todo.txt      │
  │  Desktop   │  📄 cv.pdf                                    │
  │  Downloads │                                                │
  │ Devices    │                                                │
  │  Disk      │                                                │
  └────────────┴────────────────────────────────────────────────┘
```

---

## Features

| Component | Shortcut | Description |
|---|---|---|
| **Menu Bar** | — | Replaces GNOME panel · global app menus · clock · status indicators |
| **Dock** | — | Auto-hide · icon magnification · running indicators · drag-to-rearrange |
| **Spotlight** | `Super+Space` | Apps · files · calculator · web search |
| **Launchpad** | `F4` | Fullscreen app grid with folders and search |
| **Mission Control** | `Super+Up` | All-windows overview with workspace strip |
| **Notification Center** | `Super+N` | Notification history · calendar · Do Not Disturb |
| **Control Center** | `Super+Shift+C` | WiFi · Bluetooth · volume · brightness · Night Light |
| **Finder** | — | Dual-pane file manager · Quick Look (Space) · bookmarks |
| **Show Desktop** | `Super+D` | Minimise all windows |

---

## Requirements

| Requirement | Version |
|---|---|
| Ubuntu | 24.04 LTS (Noble) |
| GNOME Shell | 46 |
| GTK4 | 4.14+ |
| Libadwaita | 1.5+ |
| Python | 3.12+ |
| Display server | X11 or Wayland |

---

## Installation

### Option 1 — Quick install (recommended)

```bash
git clone https://github.com/s1dharthpv/macux.git
cd macux
bash installer/install.sh
```

Log out and log back in. MacUX starts automatically on next login.

---

### Option 2 — Step by step

**1. Install Python dependencies**

```bash
pip3 install --user PyGObject dasbus watchdog Whoosh pulsectl Pillow appdirs tomli_w
```

**2. Clone and install**

```bash
git clone https://github.com/s1dharthpv/macux.git
cd macux
pip3 install --user .
```

**3. Install GNOME Shell extensions**

```bash
mkdir -p ~/.local/share/gnome-shell/extensions

cp -r gnome-shell/extensions/macux-mission-control@macux \
      ~/.local/share/gnome-shell/extensions/
cp -r gnome-extensions/macux-shell@macux.com \
      ~/.local/share/gnome-shell/extensions/

glib-compile-schemas ~/.local/share/gnome-shell/extensions/macux-mission-control@macux/schemas/
glib-compile-schemas ~/.local/share/gnome-shell/extensions/macux-shell@macux.com/schemas/
```

**4. Install systemd services**

```bash
mkdir -p ~/.config/systemd/user
cp data/systemd/*.service ~/.config/systemd/user/
cp installer/systemd/macux.service ~/.config/systemd/user/
cp installer/systemd/macux-spotlight-indexer.* ~/.config/systemd/user/
systemctl --user daemon-reload
```

**5. Install desktop entries**

```bash
cp data/applications/*.desktop ~/.local/share/applications/
update-desktop-database -q ~/.local/share/applications/
```

**6. Enable and start**

```bash
systemctl --user enable --now macux.service
systemctl --user enable --now macux-dock.service
systemctl --user enable --now macux-menu-bar.service
systemctl --user enable --now macux-notification-center.service
systemctl --user enable --now macux-control-center.service
systemctl --user enable --now macux-spotlight.service
```

**7. Enable GNOME Shell extensions**

```bash
gnome-extensions enable macux-mission-control@macux
gnome-extensions enable macux-shell@macux.com
```

Log out and back in.

---

### Option 3 — Development install

```bash
git clone https://github.com/s1dharthpv/macux.git
cd macux
make dev-install
```

---

### Option 4 — Debian package

```bash
git clone https://github.com/s1dharthpv/macux.git
cd macux
make deb
sudo dpkg -i ../macux_1.0.0-1_amd64.deb
```

---

## Post-install checklist

- [ ] Log out and back in (GNOME Shell extensions require a session restart)
- [ ] Run `gnome-extensions enable macux-shell@macux.com` if not auto-enabled
- [ ] Run `gnome-extensions enable macux-mission-control@macux` if not auto-enabled
- [ ] Optionally edit `~/.config/macux/config.toml` to customise

---

## Configuration

MacUX creates `~/.config/macux/config.toml` on first run. Key options:

```toml
[global]
theme = "auto"            # "light" | "dark" | "auto" (follows GNOME colour scheme)
accent_color = "#0071e3"  # hex colour for buttons, focus rings, active states
animations = true

[dock]
position = "bottom"       # "bottom" | "left" | "right"
icon_size = 48
magnification = true
auto_hide = false

[spotlight]
hotkey = "<Super>space"
max_results = 12
search_web = true

[menu_bar]
clock_format = "%H:%M"
show_battery_percentage = true

[finder]
default_view = "icon"     # "icon" | "list"
show_hidden_files = false
```

Full reference: [`config/config.toml.default`](config/config.toml.default)

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
| `Space` | Quick Look (in Finder) |

---

## Service management

```bash
# Status of all MacUX services
systemctl --user status 'macux*'

# Live logs
journalctl --user -u macux.service -f

# Restart everything
systemctl --user restart macux.service

# Stop everything
systemctl --user stop macux.service macux-dock.service \
  macux-menu-bar.service macux-spotlight.service \
  macux-notification-center.service macux-control-center.service

# CLI control
macux-ctl status
macux-ctl theme dark
macux-ctl config get global.accent_color
macux-ctl restart dock
```

---

## Uninstall

```bash
bash installer/uninstall.sh           # removes MacUX, keeps ~/.config/macux
bash installer/uninstall.sh --purge   # removes everything including config and data
```

This restores the standard GNOME panel and removes all systemd units and extensions.

---

## Development

```bash
# Run all tests (1212 tests)
pytest tests/

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Lint + type-check
make lint

# Format
make format

# Rebuild GSettings schemas after editing
make compile-schemas
```

### Project structure

```
macux/
├── macuxd/              # Core daemon + DBus service + config + SQLite
├── dock/                # GTK4 dock
├── spotlight/           # Search window + Whoosh indexer
├── launchpad/           # Fullscreen app grid
├── menu_bar/            # Global menu bar + indicators
├── control_center/      # Quick settings panel
├── notification_center/ # History panel + calendar widgets
├── mission_control/     # Window layout engine
├── finder/              # File manager + Quick Look
├── themes/              # CSS generation + color tokens + font manager
├── packaging/           # Install manifest + .desktop validator + Debian packaging
├── gnome-shell/         # macux-mission-control@macux extension
├── gnome-extensions/    # macux-shell@macux.com extension (menu bar + shortcuts)
├── data/                # .desktop entries + systemd units
├── installer/           # install.sh + uninstall.sh + Debian files
├── config/              # config.toml.default + DBus XML specs
├── tests/
│   ├── unit/            # 965 unit tests (GTK-free, fast)
│   └── integration/     # 247 integration tests
└── Makefile
```

---

## Architecture

MacUX runs as a set of cooperating processes communicating over the DBus session bus (`com.macux.*`):

```
                    ┌──────────────────────┐
                    │  macuxd (orchestrator)│
                    │  com.macux.Daemon     │
                    └──────┬───────────────┘
                           │ DBus session bus
          ┌────────────────┼────────────────────────┐
          │                │                        │
   ┌──────┴──────┐  ┌──────┴──────┐  ┌─────────────┴──┐
   │  com.macux  │  │  com.macux  │  │   com.macux     │
   │  .Dock      │  │  .Spotlight │  │   .MenuBar ...  │
   └─────────────┘  └─────────────┘  └────────────────-┘

   GNOME Shell extensions (JS):
   ┌─────────────────────────┐  ┌──────────────────────────┐
   │ macux-shell@macux.com   │  │ macux-mission-control    │
   │ (menu bar, shortcuts,   │  │ @macux                   │
   │  DBus proxy)            │  │ (window overview)        │
   └─────────────────────────┘  └──────────────────────────┘
```

Full technical design: [`docs/PHASE1_ARCHITECTURE.md`](docs/PHASE1_ARCHITECTURE.md)

---

## Compatibility

| Ubuntu | GNOME Shell | Status |
|---|---|---|
| 24.04 LTS (Noble) | 46 | Supported |
| 22.04 LTS (Jammy) | 43–44 | Not tested |
| 23.10 (Mantic) | 45 | Not tested |

---

## License

Copyright (C) 2026 Sidharth Thamban \<sidharth.thamban@gmail.com\>

Released under the [GNU General Public License v3.0 or later](https://www.gnu.org/licenses/gpl-3.0).
