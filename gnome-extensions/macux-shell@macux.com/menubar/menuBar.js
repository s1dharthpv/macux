/**
 * MacUX Menu Bar — replaces the GNOME top panel with a macOS-style menu bar.
 *
 * Architecture:
 *   - Hides the default GNOME panel
 *   - Creates a new St.BoxLayout spanning the full screen width
 *   - Left:   Apple logo + active app name + app menus (GlobalMenuProxy)
 *   - Center: Clock
 *   - Right:  System indicators (network, bluetooth, battery, volume, user)
 */

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Shell from 'gi://Shell';

const MENU_BAR_HEIGHT = 28; // pixels

export class MenuBar {
    constructor(extension, dbusProxy) {
        this._ext = extension;
        this._dbusProxy = dbusProxy;
        this._originalPanelVisible = true;
        this._clockTimerId = null;
        this._bar = null;
        this._leftBox = null;
        this._centerBox = null;
        this._rightBox = null;
        this._clockLabel = null;
    }

    enable() {
        // Hide the stock GNOME panel
        Main.panel.hide();

        this._buildBar();
        this._startClock();
        this._connectDbusSignals();
        console.log('[MacUX MenuBar] Enabled.');
    }

    disable() {
        this._stopClock();

        if (this._bar) {
            this._bar.destroy();
            this._bar = null;
        }

        // Restore stock GNOME panel
        Main.panel.show();
        console.log('[MacUX MenuBar] Disabled.');
    }

    _buildBar() {
        this._bar = new St.BoxLayout({
            name: 'macux-menu-bar',
            style_class: 'macux-menu-bar',
            x: 0,
            y: 0,
            width: global.stage.width,
            height: MENU_BAR_HEIGHT,
            reactive: true,
            can_focus: false,
        });

        // Left section
        this._leftBox = new St.BoxLayout({
            name: 'macux-menu-bar-left',
            style_class: 'macux-menu-bar-section',
            x_expand: true,
            x_align: Clutter.ActorAlign.START,
        });

        // Apple logo button
        const appleBtn = new St.Button({
            label: '',    // U+F8FF Apple logo (PUA) — fonts with SF icons render this
            style_class: 'macux-apple-button',
        });
        appleBtn.connect('clicked', () => this._showAppleMenu());
        this._leftBox.add_child(appleBtn);

        // Active app name (updated on window focus change)
        this._appNameLabel = new St.Label({
            text: 'Finder',
            style_class: 'macux-app-name',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._leftBox.add_child(this._appNameLabel);

        // Center section — clock
        this._centerBox = new St.BoxLayout({
            name: 'macux-menu-bar-center',
            style_class: 'macux-menu-bar-section',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._clockLabel = new St.Label({
            text: this._formatClock(),
            style_class: 'macux-clock',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._centerBox.add_child(this._clockLabel);

        // Right section — indicators
        this._rightBox = new St.BoxLayout({
            name: 'macux-menu-bar-right',
            style_class: 'macux-menu-bar-section',
            x_expand: true,
            x_align: Clutter.ActorAlign.END,
        });
        this._buildSystemIndicators();

        this._bar.add_child(this._leftBox);
        this._bar.add_child(this._centerBox);
        this._bar.add_child(this._rightBox);

        // Add to the chrome layer (above all windows)
        Main.layoutManager.addTopChrome(this._bar);

        // Track window focus for app name updates
        this._focusId = global.display.connect('notify::focus-window', () => {
            this._updateAppName();
        });
    }

    _buildSystemIndicators() {
        // These are placeholder labels; Phase 7 (Menu Bar) will wire real DBus indicators
        const indicators = [
            { label: '●', cls: 'macux-indicator-battery', tooltip: 'Battery' },
            { label: '▲', cls: 'macux-indicator-wifi',    tooltip: 'WiFi' },
            { label: '❯', cls: 'macux-indicator-volume',  tooltip: 'Volume' },
        ];

        for (const ind of indicators) {
            const btn = new St.Button({
                label: ind.label,
                style_class: `macux-indicator ${ind.cls}`,
                y_align: Clutter.ActorAlign.CENTER,
            });
            this._rightBox.add_child(btn);
        }
    }

    _startClock() {
        this._clockTimerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._clockLabel) {
                this._clockLabel.set_text(this._formatClock());
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopClock() {
        if (this._clockTimerId !== null) {
            GLib.source_remove(this._clockTimerId);
            this._clockTimerId = null;
        }
        if (this._focusId) {
            global.display.disconnect(this._focusId);
            this._focusId = null;
        }
    }

    _formatClock() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const d = days[now.getDay()];
        const mo = months[now.getMonth()];
        const date = now.getDate();
        return `${d} ${mo} ${date}  ${h}:${m}`;
    }

    _updateAppName() {
        const focusedWindow = global.display.get_focus_window();
        if (!focusedWindow) {
            this._appNameLabel.set_text('Finder');
            return;
        }
        const app = Shell.WindowTracker.get_default().get_window_app(focusedWindow);
        if (app) {
            this._appNameLabel.set_text(app.get_name() || 'Unknown');
        }
    }

    _connectDbusSignals() {
        this._dbusProxy?.onThemeChanged(theme => {
            this._applyTheme(theme);
        });
    }

    _applyTheme(theme) {
        if (this._bar) {
            this._bar.remove_style_class_name('macux-theme-light');
            this._bar.remove_style_class_name('macux-theme-dark');
            this._bar.add_style_class_name(`macux-theme-${theme}`);
        }
    }

    _showAppleMenu() {
        // Phase 7 will implement the full Apple menu
        console.log('[MacUX MenuBar] Apple menu (TODO: Phase 7)');
    }
}
