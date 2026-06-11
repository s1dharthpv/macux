/**
 * MacUX Global Shortcuts — registers system-wide keyboard shortcuts
 * and triggers MacUX component actions via DBus.
 *
 * Shortcuts are registered through GNOME Shell's keybinding system
 * using the extension's GSettings schema.
 */

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

// DBus names for each component
const COMPONENT_DBUS = {
    spotlight: { name: 'com.macux.Spotlight', path: '/com/macux/Spotlight', method: 'Toggle' },
    launchpad: { name: 'com.macux.Launchpad', path: '/com/macux/Launchpad', method: 'Toggle' },
    missionControl: { name: 'com.macux.MissionControl', path: '/com/macux/MissionControl', method: 'Toggle' },
    notificationCenter: { name: 'com.macux.NotificationCenter', path: '/com/macux/NotificationCenter', method: 'Toggle' },
    controlCenter: { name: 'com.macux.ControlCenter', path: '/com/macux/ControlCenter', method: 'Toggle' },
};

// Default keybindings (can be overridden by GSettings)
const DEFAULT_BINDINGS = {
    'macux-spotlight': ['<Super>space'],
    'macux-launchpad': ['F4'],
    'macux-mission-control': ['<Super>Up'],
    'macux-notification-center': ['<Super>n'],
    'macux-control-center': ['<Super><Shift>c'],
    'macux-show-desktop': ['<Super>d'],
};

const BINDING_ACTIONS = {
    'macux-spotlight': () => _triggerComponent('spotlight'),
    'macux-launchpad': () => _triggerComponent('launchpad'),
    'macux-mission-control': () => _triggerComponent('missionControl'),
    'macux-notification-center': () => _triggerComponent('notificationCenter'),
    'macux-control-center': () => _triggerComponent('controlCenter'),
    'macux-show-desktop': () => _showDesktop(),
};

function _triggerComponent(componentKey) {
    const spec = COMPONENT_DBUS[componentKey];
    if (!spec) return;
    const IFACE = `<node><interface name="${spec.name}"><method name="${spec.method}"/></interface></node>`;
    try {
        const ProxyClass = Gio.DBusProxy.makeProxyWrapper(IFACE);
        const proxy = new ProxyClass(
            Gio.DBus.session, spec.name, spec.path,
            null, null, Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        );
        proxy[`${spec.method}Async`]().catch(e => {
            console.error(`[MacUX Shortcuts] ${spec.method} failed for ${spec.name}:`, e);
        });
    } catch (e) {
        console.error(`[MacUX Shortcuts] Failed to proxy ${spec.name}:`, e);
    }
}

function _showDesktop() {
    // Minimize all windows on the current workspace
    const workspace = global.workspace_manager.get_active_workspace();
    workspace.list_windows().forEach(win => {
        if (win.get_window_type() === Meta.WindowType.NORMAL) {
            win.minimize();
        }
    });
}

export class GlobalShortcuts {
    constructor(extension, dbusProxy) {
        this._ext = extension;
        this._dbusProxy = dbusProxy;
        this._registeredBindings = [];
    }

    enable() {
        for (const [name, defaultKeys] of Object.entries(DEFAULT_BINDINGS)) {
            const action = BINDING_ACTIONS[name];
            if (!action) continue;

            try {
                Main.wm.addKeybinding(
                    name,
                    this._getSettingsForBinding(name, defaultKeys),
                    Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                    Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
                    action,
                );
                this._registeredBindings.push(name);
                console.log(`[MacUX Shortcuts] Registered: ${name}`);
            } catch (e) {
                console.error(`[MacUX Shortcuts] Failed to register ${name}:`, e);
            }
        }
    }

    disable() {
        for (const name of this._registeredBindings) {
            try {
                Main.wm.removeKeybinding(name);
            } catch (e) {
                console.error(`[MacUX Shortcuts] Failed to unregister ${name}:`, e);
            }
        }
        this._registeredBindings = [];
    }

    _getSettingsForBinding(name, defaultKeys) {
        // Try to get settings from the extension schema; fall back to in-memory settings
        try {
            return this._ext.getSettings('org.gnome.shell.extensions.macux');
        } catch (_) {
            // Schema not installed yet — use a fake settings object with defaults
            return new _FakeSettings(name, defaultKeys);
        }
    }
}

/**
 * Minimal Gio.Settings substitute for environments where the schema
 * is not yet compiled/installed. Allows the extension to load without errors.
 */
class _FakeSettings {
    constructor(name, defaultKeys) {
        this._name = name;
        this._keys = defaultKeys;
    }

    get_strv(_key) {
        return this._keys;
    }

    connect() { return 0; }
    disconnect() {}
}
