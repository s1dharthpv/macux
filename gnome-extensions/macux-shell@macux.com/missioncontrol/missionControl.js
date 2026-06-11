/**
 * MacUX Mission Control — window and workspace overview.
 *
 * Extends GNOME Shell's built-in Overview with macOS-style layout and
 * exposes a DBus interface so Python components can trigger it.
 *
 * Full implementation happens in Phase 10. This skeleton:
 *   - Registers the DBus service (com.macux.MissionControl)
 *   - Delegates to GNOME's built-in overview for now
 *   - Provides the keyboard shortcut integration hook
 */

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import Gio from 'gi://Gio';

const MC_DBUS_NAME = 'com.macux.MissionControl';
const MC_DBUS_PATH = '/com/macux/MissionControl';
const MC_DBUS_IFACE = `
<node>
  <interface name="com.macux.MissionControl">
    <method name="Show"/>
    <method name="Hide"/>
    <method name="Toggle"/>
    <method name="ShowDesktop"/>
    <property name="Visible" type="b" access="read"/>
  </interface>
</node>`;

export class MissionControl {
    constructor(extension, dbusProxy) {
        this._ext = extension;
        this._dbusProxy = dbusProxy;
        this._dbusId = 0;
        this._impl = null;
    }

    enable() {
        this._registerDbus();
        console.log('[MacUX MissionControl] Enabled (Phase 10 will add custom layout).');
    }

    disable() {
        this._unregisterDbus();
    }

    _registerDbus() {
        this._impl = Gio.DBusExportedObject.wrapJSObject(MC_DBUS_IFACE, this);
        this._impl.export(Gio.DBus.session, MC_DBUS_PATH);
        this._dbusId = Gio.DBus.session.own_name(
            MC_DBUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null, null,
        );
    }

    _unregisterDbus() {
        if (this._impl) {
            this._impl.unexport();
            this._impl = null;
        }
        if (this._dbusId) {
            Gio.DBus.session.unown_name(this._dbusId);
            this._dbusId = 0;
        }
    }

    // DBus method implementations
    Show() {
        Main.overview.show();
    }

    Hide() {
        Main.overview.hide();
    }

    Toggle() {
        if (Main.overview.visible) {
            Main.overview.hide();
        } else {
            Main.overview.show();
        }
    }

    ShowDesktop() {
        // Minimize all normal windows
        const workspace = global.workspace_manager.get_active_workspace();
        workspace.list_windows().forEach(win => {
            if (!win.minimized && win.get_window_type() === 0 /* NORMAL */) {
                win.minimize();
            }
        });
    }

    get Visible() {
        return Main.overview.visible;
    }
}
