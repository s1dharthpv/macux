/**
 * MacUX Shell Integration Extension
 * Provides: Menu Bar, Mission Control, Global Shortcuts, DBus proxy
 *
 * GNOME Shell 46 compatible.
 */

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { MenuBar } from './menubar/menuBar.js';
import { MissionControl } from './missioncontrol/missionControl.js';
import { GlobalShortcuts } from './shortcuts/globalShortcuts.js';
import { MacuxDBusProxy } from './dbus/dbusProxy.js';

export default class MacuxShellExtension extends Extension {
    constructor(metadata) {
        super(metadata);
        this._menuBar = null;
        this._missionControl = null;
        this._shortcuts = null;
        this._dbusProxy = null;
    }

    enable() {
        console.log('[MacUX] Extension enabling...');

        try {
            // DBus proxy must be first — other modules may use it
            this._dbusProxy = new MacuxDBusProxy(this);
            this._dbusProxy.init();

            this._menuBar = new MenuBar(this, this._dbusProxy);
            this._menuBar.enable();

            this._missionControl = new MissionControl(this, this._dbusProxy);
            this._missionControl.enable();

            this._shortcuts = new GlobalShortcuts(this, this._dbusProxy);
            this._shortcuts.enable();

            console.log('[MacUX] Extension enabled successfully.');
        } catch (e) {
            console.error('[MacUX] Failed to enable extension:', e);
            this.disable();
        }
    }

    disable() {
        console.log('[MacUX] Extension disabling...');

        this._shortcuts?.disable();
        this._shortcuts = null;

        this._missionControl?.disable();
        this._missionControl = null;

        this._menuBar?.disable();
        this._menuBar = null;

        this._dbusProxy?.destroy();
        this._dbusProxy = null;

        console.log('[MacUX] Extension disabled.');
    }
}
