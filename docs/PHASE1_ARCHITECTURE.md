# MacUX — Phase 1: Architecture & Technical Design Document

**Version:** 1.0.0  
**Date:** 2026-06-10  
**Platform:** Ubuntu 24.04.4 LTS · GNOME Shell 46 · GTK4 4.14 · Libadwaita 1.5  
**Author:** MacUX Engineering

---

## 1. Project Vision

MacUX is a production-quality macOS-inspired desktop experience layer for Ubuntu 24.04. It does not replace GNOME — it orchestrates on top of GNOME Shell, GTK4, and Wayland/X11 to deliver a cohesive macOS-like workflow without sacrificing Ubuntu system compatibility.

### 1.1 Design Principles

| Principle | Implementation |
|---|---|
| **Non-destructive** | Never modify core GNOME — only overlay and extend |
| **Composable** | Each component runs as an independent process/extension |
| **Reversible** | Full uninstall returns desktop to stock GNOME |
| **Performance** | 60 fps animations, <50 ms response on all interactions |
| **Accessible** | ARIA roles, keyboard navigation, screen reader support |
| **Packaged** | Every component ships as a .deb with proper systemd units |

---

## 2. System Architecture

### 2.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SPACE APPLICATIONS                   │
│              (any GTK/Qt/Electron/Web app)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    MacUX DESKTOP LAYER                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  Dock    │ │Spotlight │ │Launchpad │ │Mission Ctrl  │  │
│  │ (GTK4)  │ │ (GTK4)  │ │ (GTK4)  │ │  (GTK4)      │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │Menu Bar  │ │Notif Ctr │ │Control Ctr│ │   Finder     │  │
│  │(GS Ext) │ │ (GTK4)  │ │ (GTK4)  │ │   (GTK4)     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ DBus IPC
┌──────────────────────────▼──────────────────────────────────┐
│                  MacUX ORCHESTRATOR DAEMON                    │
│              (macuxd — Python 3.12 systemd service)          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  State Manager │ Config Manager │ Event Bus          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    SYSTEM SERVICES                            │
│  NetworkManager │ BlueZ │ UPower │ PulseAudio/PipeWire      │
│  GNOME Shell │ Mutter │ GDM │ AccountsService               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Inter-Process Communication Architecture

All MacUX components communicate via **DBus** (session bus). This provides:
- Type-safe, introspectable messaging
- Process isolation (a crashed component cannot crash others)
- Language-agnostic (GNOME Shell extensions use JS; Python components use dbus-python/dasbus)

**Primary DBus namespace:** `com.macux`

| Service | DBus Name | Object Path |
|---|---|---|
| Orchestrator | `com.macux.Daemon` | `/com/macux/Daemon` |
| Dock | `com.macux.Dock` | `/com/macux/Dock` |
| Spotlight | `com.macux.Spotlight` | `/com/macux/Spotlight` |
| Launchpad | `com.macux.Launchpad` | `/com/macux/Launchpad` |
| Mission Control | `com.macux.MissionControl` | `/com/macux/MissionControl` |
| Menu Bar | `com.macux.MenuBar` | `/com/macux/MenuBar` |
| Notification Center | `com.macux.NotificationCenter` | `/com/macux/NotificationCenter` |
| Control Center | `com.macux.ControlCenter` | `/com/macux/ControlCenter` |
| Finder | `com.macux.Finder` | `/com/macux/Finder` |

### 2.3 Event Bus Design

The orchestrator daemon implements a publish/subscribe event bus over DBus signals.

```
Event Categories:
  macux.app.*          — application lifecycle events
  macux.workspace.*    — workspace/virtual desktop events
  macux.window.*       — window state events
  macux.system.*       — system state (battery, network, etc.)
  macux.ui.*           — UI interaction events
  macux.search.*       — search events from Spotlight
  macux.notify.*       — notification events
```

---

## 3. Component Architecture

### 3.1 Dock

**Implementation:** Standalone GTK4 application running as a transparent layered window.

**Window Strategy:**
- Window type: `GDK_SURFACE_TOPLEVEL` with `_NET_WM_WINDOW_TYPE_DOCK` hint
- Positioned at bottom-center using `Gdk.Surface.move()` + monitor geometry
- Layer: above normal windows, below fullscreen
- Input region: only dock icon strip (passthrough for surrounding areas)

**Architecture:**
```
DockApplication (Adw.Application)
    └── DockWindow (Gtk.ApplicationWindow)
            ├── DockBackground (Gtk.Fixed) — glassmorphism layer
            ├── DockBox (Gtk.Box, horizontal)
            │     ├── PinnedAppsSection (Gtk.Box)
            │     │     └── DockIcon[] — each icon is DockButton widget
            │     ├── DockSeparator (Gtk.Separator)
            │     └── RunningAppsSection (Gtk.Box)
            │           └── DockIcon[] — dynamically populated
            └── DockTrash (DockButton) — rightmost
```

**State:** Stored in SQLite `dock.db`. Schema in §5.1.

**Key Features:**
- Magnification via `Gtk.Widget.set_size_request()` + CSS transform on hover proximity
- Auto-hide: monitor cursor position via `GDK_POINTER_MOTION_MASK`, slide dock in/out with `Adw.TimedAnimation`
- Running indicators: poll `Wnck.Screen.get_windows()` for running apps, match by `.desktop` file
- Drag-and-drop: `Gtk.DragSource` + `Gtk.DropTarget` for rearranging, `Gdk.FileList` for app drops

---

### 3.2 Spotlight Search

**Implementation:** Standalone GTK4 overlay application (always-on-top, centered).

**Architecture:**
```
SpotlightApplication (Adw.Application)
    └── SpotlightWindow (Gtk.Window, no decoration)
            ├── SearchEntry (Gtk.SearchEntry)
            ├── ResultsPane (Gtk.ScrolledWindow)
            │     └── ResultsListBox (Gtk.ListBox)
            │           └── ResultRow[] (Gtk.ListBoxRow)
            │                 ├── CategoryHeader
            │                 └── ResultItem
            └── PreviewPane (Gtk.Stack)
```

**Search Backend:**
- **App search:** `.desktop` file parser + XDG application database
- **File search:** Whoosh full-text index over home directory, refreshed by inotify watcher
- **Calculator:** Python `ast.literal_eval` for safe expression evaluation
- **Web:** Opens default browser with search query
- **Commands:** Whitelist-based command runner

**Index Strategy:**
```
SpotlightIndex (Whoosh Schema):
  - path: ID (stored=True)
  - name: TEXT (analyzer=StemmingAnalyzer)
  - content: TEXT (analyzer=StemmingAnalyzer)
  - type: KEYWORD (stored=True) — app|file|folder|contact
  - mtime: NUMERIC (stored=True)
  - icon: STORED
```

**Keyboard Trigger:** Global shortcut registered via GNOME Shell extension `com.macux.shortcuts` that sends DBus signal `com.macux.Spotlight.Show()`.

---

### 3.3 Launchpad

**Implementation:** Fullscreen GTK4 overlay with blur-behind effect.

**Architecture:**
```
LaunchpadApplication (Adw.Application)
    └── LaunchpadWindow (Gtk.Window, fullscreen)
            ├── BackgroundBlur (Gtk.Fixed) — snapshot compositor blur
            ├── SearchBar (Gtk.SearchEntry)
            ├── PageCarousel (Adw.Carousel)
            │     └── AppPage[] (Gtk.Grid, 6×4 layout)
            │           └── AppIcon[] (LaunchpadAppButton)
            └── PageDots (Adw.CarouselIndicatorDots)
```

**App Discovery:** Reads all `.desktop` files from:
- `/usr/share/applications/`
- `/usr/local/share/applications/`
- `~/.local/share/applications/`

Filtered by `NoDisplay=false`, sorted by name, paginated at 24 apps/page.

**Folder Groups:** Stored in SQLite `launchpad.db`. Users drag icons onto each other to create folders.

---

### 3.4 Mission Control

**Implementation:** GNOME Shell extension (JavaScript) — must live inside GNOME Shell for Mutter API access.

**Architecture:**
```
MissionControlExtension (GNOME Shell Extension)
    ├── OverviewMode — triggers Mutter window compositor effects
    ├── WorkspaceBar — top strip of workspace thumbnails  
    ├── WindowGrid — tiled preview of all windows on current workspace
    └── DBusProxy — exposes com.macux.MissionControl interface
```

**Why a GNOME Shell extension here?** Window compositor effects (blur, scale, rearrange) require Mutter's `WindowManager` and `WorkspaceManager` APIs, which are only accessible from within GNOME Shell's process. No standalone GTK4 app can replicate this.

**Keyboard Trigger:** `Super+Up` / `F3` → calls `com.macux.MissionControl.Toggle()`

---

### 3.5 Menu Bar

**Implementation:** GNOME Shell extension panel — replaces the top GNOME Shell panel.

**Architecture:**
```
MenuBarExtension (GNOME Shell Extension)
    ├── AppMenuIndicator — left side: Apple logo + active app name + app menus
    │     └── GlobalMenuProxy — reads DBus menu from focused window (appmenu-gtk-module)
    ├── ClockIndicator — center: HH:MM [weekday date]
    └── SystemTray — right side (LTR):
          ├── NotificationBell
          ├── ControlCenterToggle
          ├── NetworkIndicator
          ├── BluetoothIndicator
          ├── BatteryIndicator
          ├── VolumeIndicator
          └── UserMenuIndicator
```

**Global Menu:** Apps must export their menu via `com.canonical.AppMenu` DBus protocol. Install `appmenu-gtk-module` to auto-export GTK3/GTK4 menus.

---

### 3.6 Notification Center

**Implementation:** Standalone GTK4 panel that slides in from the right.

**Architecture:**
```
NotificationCenterApplication (Adw.Application)
    └── NotificationCenterWindow (Gtk.Window, side panel)
            ├── DateTimeHeader (Gtk.Box)
            │     ├── CalendarWidget (Gtk.Calendar)
            │     └── DateLabel (Gtk.Label)
            ├── WidgetSection (Gtk.Box, horizontal)
            │     ├── WeatherWidget
            │     ├── ClockWidget (analog)
            │     └── NotesWidget
            └── NotificationList (Gtk.ScrolledWindow)
                  └── NotificationGroup[] (Gtk.Box)
                        └── NotificationCard[] (Gtk.Frame)
```

**Notification Source:** Implements `org.freedesktop.Notifications` DBus service (intercepts system notifications), stores to SQLite `notifications.db`.

---

### 3.7 Control Center

**Implementation:** Standalone GTK4 popover panel anchored to the menu bar.

**Architecture:**
```
ControlCenterApplication (Adw.Application)
    └── ControlCenterWindow (Gtk.Popover-style window)
            ├── Row1: WiFiButton | BluetoothButton | AirDropButton | FocusButton
            ├── Row2: VolumeSlider | BrightnessSlider
            ├── Row3: NightLightToggle | BatteryStatus | VPNStatus
            └── QuickLinks: SystemPrefs | Display | Sound
```

**System Integration:**
- WiFi: NetworkManager via `NM.Client` (libnm GObject introspection)
- Bluetooth: BlueZ via DBus `org.bluez`
- Volume: PulseAudio/PipeWire via `pulsectl` Python library
- Brightness: `brightnessctl` subprocess or DDC/CI via `ddcutil`
- Battery: UPower via `UPower.Device` GObject

---

### 3.8 Finder Alternative (MacUX Finder)

**Implementation:** Full standalone GTK4 application.

**Architecture:**
```
FinderApplication (Adw.Application)
    └── FinderWindow (Adw.ApplicationWindow)
            ├── HeaderBar (Adw.HeaderBar)
            │     ├── BackForwardButtons
            │     ├── ViewToggle (Icon|List|Column|Gallery)
            │     └── SearchEntry
            ├── ContentPane (Adw.NavigationSplitView)
            │     ├── Sidebar (Gtk.ListBox)
            │     │     ├── FavoritesSection
            │     │     ├── iCloud Section (stub)
            │     │     ├── LocationsSection (drives, network)
            │     │     └── TagsSection
            │     └── MainView (Gtk.Stack)
            │           ├── IconView (Gtk.GridView)
            │           ├── ListView (Gtk.ColumnView)
            │           ├── ColumnView (multi-pane, Miller columns)
            │           └── GalleryView (Gtk.GridView, large previews)
            └── PreviewPanel (Gtk.Box)
                  ├── ThumbnailPreview
                  ├── FileMetadata
                  └── QuickActions
```

**File Operations:** GIO (`Gio.File`) for all file operations — native async, Trash support, network filesystems.

**Search Backend:** Shared Whoosh index with Spotlight.

**Tagging:** SQLite `finder.db` — extended attributes via `pyxattr` for disk persistence.

---

## 4. Shared Infrastructure

### 4.1 MacUX Orchestrator Daemon (`macuxd`)

The central daemon coordinates all components, manages shared state, and owns the DBus session names.

```python
# Responsibilities:
# 1. Own com.macux.Daemon DBus name
# 2. Start/stop/restart child components
# 3. Broadcast system events to all components
# 4. Manage global config (XDG_CONFIG_HOME/macux/config.toml)
# 5. Handle global shortcut registration delegation
# 6. Watchdog: restart crashed components
```

**Systemd Unit:** `macux.service` (user session service, `WantedBy=graphical-session.target`)

### 4.2 Configuration System

Single source of truth: `~/.config/macux/config.toml`

```toml
[global]
theme = "light"               # light | dark | auto
accent_color = "#0071e3"
font_family = "SF Pro Display"
font_size = 13
animations = true
animation_speed = 1.0         # multiplier

[dock]
position = "bottom"           # bottom | left | right
icon_size = 48
magnification = true
magnification_max = 72
auto_hide = false
auto_hide_delay = 0.5
show_running_indicators = true
show_recent_apps = true
recent_apps_count = 3

[spotlight]
hotkey = "<Super>space"
max_results = 12
search_web = true
search_engine = "https://www.google.com/search?q={}"
index_home = true
index_depth = 5

[launchpad]
hotkey = "F4"
columns = 6
rows = 4
background_blur = true
background_opacity = 0.85

[menu_bar]
clock_format = "%H:%M"
show_date = true
show_battery_percentage = true
show_wifi_name = false

[notification_center]
hotkey = "<Super>n"
do_not_disturb = false
banner_timeout = 5
max_history = 100

[mission_control]
hotkey = "<Super>Up"
show_desktop_hotkey = "<Super>d"
```

### 4.3 Theme Engine

**GTK4 CSS Variables** (custom properties for runtime theming):

```css
/* ~/.config/macux/themes/current/gtk4.css */
@define-color macux_bg_primary    #f5f5f7;
@define-color macux_bg_secondary  #ffffff;
@define-color macux_accent        #0071e3;
@define-color macux_text_primary  #1d1d1f;
@define-color macux_text_secondary #6e6e73;
@define-color macux_glass_bg      rgba(255,255,255,0.6);
@define-color macux_glass_border  rgba(255,255,255,0.8);
@define-color macux_shadow        rgba(0,0,0,0.12);
@define-color macux_separator     rgba(0,0,0,0.08);
```

**Theme Engine Architecture:**
```
ThemeEngine
    ├── ThemeLoader       — reads config.toml, applies color scheme
    ├── CSSGenerator      — generates component-specific CSS at runtime
    ├── IconThemeManager  — manages icon cache, fallback chain
    └── FontManager       — handles font loading, SF Pro substitution
```

**Font Strategy:** SF Pro is Apple-proprietary. MacUX uses **Inter** (open source, near-identical metrics) with optional SF Pro override if user installs it.

---

## 5. Database Schemas

### 5.1 Dock Database (`~/.local/share/macux/dock.db`)

```sql
CREATE TABLE pinned_apps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    desktop_id  TEXT    NOT NULL UNIQUE,  -- e.g. 'org.gnome.Calculator.desktop'
    position    INTEGER NOT NULL,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE running_app_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    desktop_id  TEXT    NOT NULL,
    last_used   DATETIME DEFAULT CURRENT_TIMESTAMP,
    use_count   INTEGER DEFAULT 1
);

CREATE INDEX idx_running_history_desktop ON running_app_history(desktop_id);
CREATE INDEX idx_pinned_position ON pinned_apps(position);
```

### 5.2 Launchpad Database (`~/.local/share/macux/launchpad.db`)

```sql
CREATE TABLE app_layout (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    desktop_id  TEXT    NOT NULL UNIQUE,
    page        INTEGER NOT NULL DEFAULT 0,
    row         INTEGER NOT NULL DEFAULT 0,
    col         INTEGER NOT NULL DEFAULT 0,
    folder_id   INTEGER REFERENCES folders(id) ON DELETE SET NULL
);

CREATE TABLE folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    page        INTEGER NOT NULL DEFAULT 0,
    row         INTEGER NOT NULL DEFAULT 0,
    col         INTEGER NOT NULL DEFAULT 0,
    color       TEXT    DEFAULT '#808080'
);

CREATE INDEX idx_layout_page ON app_layout(page, row, col);
```

### 5.3 Notifications Database (`~/.local/share/macux/notifications.db`)

```sql
CREATE TABLE notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name    TEXT    NOT NULL,
    app_icon    TEXT,
    summary     TEXT    NOT NULL,
    body        TEXT,
    actions     TEXT,               -- JSON array
    hints       TEXT,               -- JSON object
    replaces_id INTEGER,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    read_at     DATETIME,
    dismissed   BOOLEAN DEFAULT 0,
    urgency     INTEGER DEFAULT 1   -- 0=low, 1=normal, 2=critical
);

CREATE TABLE do_not_disturb_schedule (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enabled     BOOLEAN DEFAULT 0,
    start_time  TEXT DEFAULT '22:00',
    end_time    TEXT DEFAULT '07:00',
    days        TEXT DEFAULT '0,1,2,3,4,5,6'  -- bitmask as CSV
);

CREATE INDEX idx_notifications_app ON notifications(app_name);
CREATE INDEX idx_notifications_received ON notifications(received_at DESC);
CREATE INDEX idx_notifications_unread ON notifications(read_at) WHERE read_at IS NULL;
```

### 5.4 Finder Database (`~/.local/share/macux/finder.db`)

```sql
CREATE TABLE favorites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL UNIQUE,
    label       TEXT,
    icon        TEXT,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    color       TEXT    NOT NULL DEFAULT '#808080'
);

CREATE TABLE file_tags (
    file_path   TEXT    NOT NULL,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (file_path, tag_id)
);

CREATE TABLE recent_locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL UNIQUE,
    visited_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_file_tags_path ON file_tags(file_path);
CREATE INDEX idx_recent_locations_visited ON recent_locations(visited_at DESC);
```

### 5.5 Spotlight Index (`~/.local/share/macux/spotlight/`)

Whoosh index directory. Schema:

```python
from whoosh.fields import Schema, ID, TEXT, KEYWORD, NUMERIC, STORED
from whoosh.analysis import StemmingAnalyzer

SPOTLIGHT_SCHEMA = Schema(
    path     = ID(stored=True, unique=True),
    name     = TEXT(stored=True, analyzer=StemmingAnalyzer()),
    content  = TEXT(analyzer=StemmingAnalyzer()),
    type     = KEYWORD(stored=True),       # app|file|folder|image|doc
    mtime    = NUMERIC(stored=True),
    size     = NUMERIC(stored=True),
    icon     = STORED(),                   # serialized icon path
    desktop_id = STORED(),                 # for apps only
)
```

---

## 6. DBus API Contracts

### 6.1 Orchestrator Interface

```xml
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="com.macux.Daemon">
    <method name="GetVersion">
      <arg name="version" type="s" direction="out"/>
    </method>
    <method name="GetConfig">
      <arg name="key" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="SetConfig">
      <arg name="key" type="s" direction="in"/>
      <arg name="value" type="v" direction="in"/>
    </method>
    <method name="RestartComponent">
      <arg name="component" type="s" direction="in"/>
    </method>
    <method name="GetComponentStatus">
      <arg name="component" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <signal name="ConfigChanged">
      <arg name="key" type="s"/>
      <arg name="value" type="v"/>
    </signal>
    <signal name="ThemeChanged">
      <arg name="theme" type="s"/>
    </signal>
    <signal name="ComponentStateChanged">
      <arg name="component" type="s"/>
      <arg name="state" type="s"/>
    </signal>
  </interface>
</node>
```

### 6.2 Dock Interface

```xml
<interface name="com.macux.Dock">
  <method name="Show"/>
  <method name="Hide"/>
  <method name="ToggleAutoHide"/>
  <method name="PinApp">
    <arg name="desktop_id" type="s" direction="in"/>
    <arg name="position" type="i" direction="in"/>
  </method>
  <method name="UnpinApp">
    <arg name="desktop_id" type="s" direction="in"/>
  </method>
  <method name="SetPosition">
    <arg name="position" type="s" direction="in"/>
  </method>
  <method name="Bounce">
    <arg name="desktop_id" type="s" direction="in"/>
    <arg name="type" type="s" direction="in"/>
  </method>
  <signal name="AppPinned">
    <arg name="desktop_id" type="s"/>
  </signal>
  <signal name="AppUnpinned">
    <arg name="desktop_id" type="s"/>
  </signal>
  <property name="AutoHide" type="b" access="readwrite"/>
  <property name="IconSize" type="i" access="readwrite"/>
  <property name="Position" type="s" access="readwrite"/>
</interface>
```

### 6.3 Spotlight Interface

```xml
<interface name="com.macux.Spotlight">
  <method name="Show"/>
  <method name="Hide"/>
  <method name="Search">
    <arg name="query" type="s" direction="in"/>
    <arg name="results" type="aa{sv}" direction="out"/>
  </method>
  <method name="RebuildIndex"/>
  <signal name="Shown"/>
  <signal name="Hidden"/>
  <signal name="SearchCompleted">
    <arg name="query" type="s"/>
    <arg name="result_count" type="i"/>
  </signal>
</interface>
```

### 6.4 Notification Center Interface

```xml
<interface name="com.macux.NotificationCenter">
  <method name="Show"/>
  <method name="Hide"/>
  <method name="Toggle"/>
  <method name="ClearAll"/>
  <method name="GetUnreadCount">
    <arg name="count" type="i" direction="out"/>
  </method>
  <method name="SetDoNotDisturb">
    <arg name="enabled" type="b" direction="in"/>
  </method>
  <signal name="NotificationReceived">
    <arg name="id" type="i"/>
    <arg name="app_name" type="s"/>
    <arg name="summary" type="s"/>
  </signal>
  <signal name="UnreadCountChanged">
    <arg name="count" type="i"/>
  </signal>
  <property name="DoNotDisturb" type="b" access="readwrite"/>
</interface>
```

---

## 7. GNOME Shell Extension Architecture

Two extensions are required (Mission Control + Menu Bar must run inside GNOME Shell):

### 7.1 `macux-shell@macux.com`

Unified extension handling both Menu Bar and Mission Control.

```
macux-shell@macux.com/
    ├── extension.js          — entry point, imports modules
    ├── metadata.json         — extension manifest
    ├── menubar/
    │     ├── menuBar.js      — top panel replacement
    │     ├── appMenu.js      — app menu + global menu proxy
    │     ├── systemTray.js   — status indicators
    │     └── globalMenu.js   — DBus AppMenu consumer
    ├── missioncontrol/
    │     ├── missionControl.js  — overview mode
    │     ├── windowGrid.js      — window tile layout
    │     └── workspaceBar.js    — workspace thumbnails
    ├── shortcuts/
    │     └── globalShortcuts.js — register all global hotkeys
    └── dbus/
          └── dbusProxy.js    — expose com.macux.* interfaces to Shell
```

**metadata.json:**
```json
{
  "uuid": "macux-shell@macux.com",
  "name": "MacUX Shell Integration",
  "description": "MacUX menu bar, mission control, and global shortcuts",
  "version": 1,
  "shell-version": ["46"],
  "url": "https://github.com/macux/macux",
  "settings-schema": "org.gnome.shell.extensions.macux"
}
```

---

## 8. Build System

### 8.1 Project Layout (Final)

```
macux/
├── macuxd/                     — orchestrator daemon
│   ├── __init__.py
│   ├── daemon.py               — main daemon entry point
│   ├── config.py               — config loader/watcher
│   ├── eventbus.py             — DBus event publisher
│   ├── watchdog.py             — component health monitor
│   └── dbus_service.py         — com.macux.Daemon implementation
├── dock/                       — Dock component
│   ├── __init__.py
│   ├── __main__.py
│   ├── application.py
│   ├── window.py
│   ├── dock_icon.py
│   ├── animation.py
│   ├── db.py
│   ├── dbus_service.py
│   └── tests/
├── spotlight/                  — Spotlight component
├── launchpad/                  — Launchpad component
├── mission_control/            — Python DBus bridge (extension does the actual work)
├── menu_bar/                   — Python DBus bridge
├── notification_center/        — Notification Center component
├── control_center/             — Control Center component
├── finder/                     — Finder component
├── themes/
│   ├── gtk4/
│   │   ├── light.css
│   │   └── dark.css
│   ├── gnome-shell/
│   │   ├── gnome-shell.css
│   │   └── gnome-shell-dark.css
│   ├── icons/                  — MacUX icon theme (Papirus-based)
│   └── cursors/                — macOS-style cursor theme
├── assets/
│   ├── fonts/                  — Inter font files
│   ├── icons/                  — SVG app icons
│   ├── images/                 — wallpapers, backgrounds
│   └── sounds/                 — UI sound effects (ogg)
├── gnome-extensions/
│   └── macux-shell@macux.com/  — GNOME Shell extension
├── installer/
│   ├── install.sh              — one-shot installer
│   ├── uninstall.sh
│   ├── debian/                 — Debian packaging
│   │   ├── control
│   │   ├── rules
│   │   ├── changelog
│   │   └── install
│   └── systemd/
│       ├── macux.service       — user session service
│       └── macux-spotlight-indexer.service
├── config/
│   ├── config.toml.default     — shipped default config
│   └── dbus/
│       ├── com.macux.Daemon.xml
│       ├── com.macux.Dock.xml
│       └── ...
├── docs/
│   ├── PHASE1_ARCHITECTURE.md  (this file)
│   └── ...
├── tests/
│   ├── unit/
│   └── integration/
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

### 8.2 Python Dependencies (`requirements.txt`)

```
# Core
dasbus>=1.6          # modern Python DBus library
PyGObject>=3.48      # GTK4/GLib bindings
tomllib>=1.0         # TOML config (stdlib in Python 3.11+)
watchdog>=4.0        # filesystem change monitoring

# Search
Whoosh>=2.7          # full-text search engine

# System integration
pulsectl>=23.5       # PulseAudio/PipeWire control
pyxattr>=0.8         # extended filesystem attributes for tags

# Networking (DBus bindings already via GObject for NM/BlueZ)
# NetworkManager: via GObject introspection (libnm)
# BlueZ: via dbus directly
# UPower: via dbus directly

# Packaging/Utils
appdirs>=1.4         # XDG-compliant data dirs
Pillow>=10.0         # image processing for thumbnails/icons
```

### 8.3 Systemd Service (`macux.service`)

```ini
[Unit]
Description=MacUX Desktop Environment Orchestrator
PartOf=graphical-session.target
After=graphical-session.target
Requires=dbus.socket

[Service]
Type=dbus
BusName=com.macux.Daemon
ExecStart=/usr/bin/macuxd
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
```

---

## 9. Security Model

| Surface | Risk | Mitigation |
|---|---|---|
| Command execution (Spotlight) | Arbitrary code execution | Strict whitelist, no shell=True, sandboxed subprocess |
| File indexing | Privacy (sensitive files indexed) | Respect `.macuxignore`, skip `~/.ssh`, `~/.gnupg`, `~/.config/macux` |
| DBus API | Unauthorized component control | Session bus only (no system bus exposure), peer credentials checked |
| Config file | Config injection | TOML parser (no eval), schema validation on load |
| DnD file drops | Path traversal | `Gio.File` with canonical path resolution |
| Plugin/extension | Untrusted code | No plugin system in v1 |

---

## 10. Performance Targets

| Metric | Target | Measurement Method |
|---|---|---|
| Dock render time | <16 ms/frame (60 fps) | GTK4 profiler, `GSK_DEBUG=diffing` |
| Spotlight first result | <200 ms | `time.perf_counter()` in search backend |
| Launchpad open animation | <300 ms | Frame timing in `Adw.TimedAnimation` |
| Spotlight index build | <60 s (full home dir) | Benchmark script |
| Daemon startup | <2 s | `systemd-analyze blame` |
| Memory (all components) | <150 MB RSS | `ps aux` + valgrind |

---

## 11. Testing Strategy

### Unit Tests (pytest)
- Config loader: parse, validate, merge, serialize
- DB layer: CRUD for all schemas
- Search backend: indexing, querying, result ranking
- Theme engine: CSS generation, color derivation
- DBus service: method dispatch, signal emission (with mocked bus)

### Integration Tests
- Dock ↔ Daemon: pin/unpin round-trip over real DBus
- Spotlight: full index-build → search cycle
- Notification Center: receive → store → display → dismiss
- Finder: browse → tag → favorite round-trip

### UI Tests (dogtail / AT-SPI)
- Dock icon magnification on hover
- Spotlight keyboard navigation
- Launchpad page swipe and search filter

---

## 12. Phase Completion Criteria

Phase 1 is complete when:

- [x] Architecture document finalized (this document)
- [ ] Project directory structure created
- [ ] Base Python package scaffold (`setup.py`, `pyproject.toml`)
- [ ] Default config file created (`config.toml.default`)
- [ ] All DBus XML interface definitions written
- [ ] Systemd unit files written
- [ ] `requirements.txt` complete
- [ ] Orchestrator daemon skeleton (starts, acquires DBus name, exits cleanly)
- [ ] SQLite schema migration runner implemented
- [ ] Theme CSS variables defined for light + dark
- [ ] GNOME Shell extension manifest (`metadata.json`) created
- [ ] `README.md` with installation instructions written
- [ ] CI configuration (GitHub Actions) for lint + unit tests

---

*End of Phase 1 — Architecture & Technical Design Document*
