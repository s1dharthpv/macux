/**
 * MacUX Mission Control — GNOME Shell 46 extension
 *
 * Spreads all non-minimized windows of the active workspace into a grid view,
 * overlays a workspace-switcher bar at the bottom, and restores everything on
 * click / Escape / workspace switch.
 *
 * Triggers:
 *   • Hot corner — top-left (1 × 1 px reactive actor at (0, 0))
 *   • Keyboard  — Super+F3 (configurable via GSettings)
 *   • DBus      — com.macux.MissionControl.Activate / Toggle
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// ── DBus interface XML (subset we expose to the Python companion) ─────────────
const MC_IFACE = `
<node>
  <interface name="com.macux.MissionControl">
    <method name="Activate"/>
    <method name="Deactivate"/>
    <method name="Toggle"/>
    <property name="Active" type="b" access="read"/>
    <signal name="Activated"/>
    <signal name="Deactivated"/>
    <signal name="WindowSelected">
      <arg type="u" name="xid"/>
    </signal>
  </interface>
</node>`;

// ── DBus implementation ────────────────────────────────────────────────────────
class MissionControlDBusImpl {
    constructor(extension) {
        this._ext = extension;
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(MC_IFACE, this);
    }

    Activate()    { this._ext._activate();   }
    Deactivate()  { this._ext._deactivate(); }
    Toggle()      { this._ext._toggle();     }

    get Active()  { return this._ext._active; }

    export(connection) {
        this._dbusImpl.export(connection, '/com/macux/MissionControl');
    }

    unexport() {
        this._dbusImpl.unexport();
    }

    emitActivated()              { this._dbusImpl.emit_signal('Activated', null); }
    emitDeactivated()            { this._dbusImpl.emit_signal('Deactivated', null); }
    emitWindowSelected(xid)      {
        this._dbusImpl.emit_signal('WindowSelected',
            GLib.Variant.new_tuple([GLib.Variant.new_uint32(xid)]));
    }
}

// ── Main extension class ───────────────────────────────────────────────────────
export default class MissionControlExtension extends Extension {
    constructor(metadata) {
        super(metadata);
        this._active = false;
        this._savedStates = new Map();   // Meta.Window → {x, y, scaleX, scaleY}
        this._titleLabels = [];
        this._overlayActors = [];
        this._switcherBar = null;
        this._hotCornerActor = null;
        this._keyBinding = null;
        this._dbusImpl = null;
        this._ownerId = 0;
        this._connectionIds = [];
        this._settings = null;
    }

    enable() {
        this._settings = this.getSettings();
        this._setupHotCorner();
        this._setupKeybinding();
        this._setupDBus();
        this._connectWorkspaceSignals();
    }

    disable() {
        this._deactivate();
        this._teardownHotCorner();
        this._teardownKeybinding();
        this._teardownDBus();
        this._disconnectWorkspaceSignals();
        this._settings = null;
    }

    // ── Hot corner ──────────────────────────────────────────────────────────────

    _setupHotCorner() {
        if (!this._settings.get_boolean('hot-corner-enabled'))
            return;
        this._hotCornerActor = new St.Widget({
            width: 2,
            height: 2,
            reactive: true,
            opacity: 0,
        });
        Main.uiGroup.add_child(this._hotCornerActor);
        this._hotCornerActor.set_position(0, 0);
        this._hotCornerActor.connect('enter-event', () => {
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
                if (this._hotCornerActor) this._toggle();
                return GLib.SOURCE_REMOVE;
            });
        });
    }

    _teardownHotCorner() {
        if (this._hotCornerActor) {
            Main.uiGroup.remove_child(this._hotCornerActor);
            this._hotCornerActor.destroy();
            this._hotCornerActor = null;
        }
    }

    // ── Keybinding ──────────────────────────────────────────────────────────────

    _setupKeybinding() {
        Main.wm.addKeybinding(
            'toggle-shortcut',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._toggle(),
        );
        this._keyBinding = 'toggle-shortcut';
    }

    _teardownKeybinding() {
        if (this._keyBinding) {
            Main.wm.removeKeybinding(this._keyBinding);
            this._keyBinding = null;
        }
    }

    // ── DBus ────────────────────────────────────────────────────────────────────

    _setupDBus() {
        this._dbusImpl = new MissionControlDBusImpl(this);
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            'com.macux.MissionControl',
            Gio.BusNameOwnerFlags.NONE,
            (connection) => {
                this._dbusImpl.export(connection);
            },
            null,
            null,
        );
    }

    _teardownDBus() {
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
    }

    // ── Workspace signals ───────────────────────────────────────────────────────

    _connectWorkspaceSignals() {
        const wm = global.workspace_manager;
        this._connectionIds.push(
            wm.connect('active-workspace-changed', () => {
                if (this._active) this._deactivate();
            })
        );
        // Escape key handler
        this._connectionIds.push(
            global.stage.connect('key-press-event', (_actor, event) => {
                if (this._active && event.get_key_symbol() === Clutter.KEY_Escape) {
                    this._deactivate();
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            })
        );
    }

    _disconnectWorkspaceSignals() {
        const wm = global.workspace_manager;
        for (const id of this._connectionIds)
            wm.disconnect(id);
        this._connectionIds = [];
    }

    // ── Core toggle / activate / deactivate ────────────────────────────────────

    _toggle() {
        if (this._active)
            this._deactivate();
        else
            this._activate();
    }

    _activate() {
        if (this._active)
            return;
        this._active = true;

        const workspace = global.workspace_manager.get_active_workspace();
        const windows = workspace.list_windows().filter(
            w => !w.is_skip_taskbar() && !w.minimized
        );

        if (windows.length === 0) {
            this._active = false;
            return;
        }

        const duration = this._settings
            ? this._settings.get_int('animation-duration-ms')
            : 220;
        const showTitles = this._settings
            ? this._settings.get_boolean('show-window-titles')
            : true;

        this._spreadWindows(windows, duration, showTitles);
        this._showWorkspaceSwitcher();

        if (this._dbusImpl)
            this._dbusImpl.emitActivated();
    }

    _deactivate() {
        if (!this._active)
            return;
        this._active = false;

        const duration = this._settings
            ? this._settings.get_int('animation-duration-ms')
            : 220;

        this._restoreWindows(duration);
        this._removeOverlays();
        this._hideWorkspaceSwitcher();

        if (this._dbusImpl)
            this._dbusImpl.emitDeactivated();
    }

    // ── Window spreading ────────────────────────────────────────────────────────

    _spreadWindows(windows, duration, showTitles) {
        const n = windows.length;
        const cols = Math.ceil(Math.sqrt(n));
        const rows = Math.ceil(n / cols);
        const padding = 20;
        const bottomReserve = 100;

        const sw = global.screen_width;
        const sh = global.screen_height;
        const cellW = (sw - 2 * padding) / cols;
        const cellH = (sh - bottomReserve - 2 * padding) / rows;
        const inset = padding / 2;

        windows.forEach((win, i) => {
            const actor = win.get_compositor_private();
            if (!actor) return;

            // Save original state
            this._savedStates.set(win, {
                x: actor.x, y: actor.y,
                scaleX: actor.scale_x, scaleY: actor.scale_y,
                pivotX: actor.pivot_point.x, pivotY: actor.pivot_point.y,
            });

            const col = i % cols;
            const row = Math.floor(i / cols);

            const tileX = padding + col * cellW + inset;
            const tileY = padding + row * cellH + inset;
            const tileW = cellW - 2 * inset;
            const tileH = cellH - 2 * inset;

            const srcW = actor.width  || 1;
            const srcH = actor.height || 1;
            const scale = Math.min(tileW / srcW, tileH / srcH, 1.0);

            const destX = tileX + (tileW - srcW * scale) / 2;
            const destY = tileY + (tileH - srcH * scale) / 2;

            actor.set_pivot_point(0, 0);
            actor.ease({
                x: destX, y: destY,
                scale_x: scale, scale_y: scale,
                duration,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });

            // Click-to-select overlay
            const overlay = new St.Widget({
                reactive: true,
                x: destX, y: destY,
                width: srcW * scale,
                height: srcH * scale,
                style: 'border-radius: 8px;',
                opacity: 0,
            });
            overlay.connect('button-press-event', () => {
                this._selectWindow(win);
                return Clutter.EVENT_STOP;
            });
            overlay.connect('enter-event', () => {
                overlay.ease({ opacity: 30, duration: 120 });
            });
            overlay.connect('leave-event', () => {
                overlay.ease({ opacity: 0, duration: 120 });
            });
            Main.uiGroup.add_child(overlay);
            this._overlayActors.push(overlay);

            // Window title label
            if (showTitles) {
                const lbl = new St.Label({
                    text: win.title || win.get_wm_class() || '',
                    style: 'font-size: 11px; color: white; text-shadow: 0 1px 4px black; max-width: 200px;',
                    x_align: Clutter.ActorAlign.CENTER,
                });
                Main.uiGroup.add_child(lbl);
                lbl.set_position(
                    destX + (srcW * scale - lbl.width) / 2,
                    destY + srcH * scale + 4,
                );
                this._titleLabels.push(lbl);
                this._overlayActors.push(lbl);
            }
        });
    }

    _selectWindow(win) {
        const actor = win.get_compositor_private();
        if (!actor) { this._deactivate(); return; }

        const xid = win.get_id ? win.get_id() : 0;
        if (this._dbusImpl) this._dbusImpl.emitWindowSelected(xid);

        this._deactivate();

        // Activate the selected window after restore animation completes
        const duration = this._settings
            ? this._settings.get_int('animation-duration-ms')
            : 220;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, duration + 50, () => {
            win.activate(global.get_current_time());
            return GLib.SOURCE_REMOVE;
        });
    }

    _restoreWindows(duration) {
        for (const [win, state] of this._savedStates) {
            const actor = win.get_compositor_private();
            if (!actor) continue;
            actor.set_pivot_point(state.pivotX, state.pivotY);
            actor.ease({
                x: state.x, y: state.y,
                scale_x: state.scaleX, scale_y: state.scaleY,
                duration,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        }
        this._savedStates.clear();
    }

    _removeOverlays() {
        for (const actor of this._overlayActors)
            actor.destroy();
        this._overlayActors = [];
        this._titleLabels = [];
    }

    // ── Workspace switcher bar ──────────────────────────────────────────────────

    _showWorkspaceSwitcher() {
        this._switcherBar = new St.BoxLayout({
            vertical: false,
            style: [
                'background-color: rgba(0,0,0,0.55)',
                'border-radius: 10px',
                'padding: 6px 10px',
                'spacing: 8px',
            ].join(';'),
        });

        const wm = global.workspace_manager;
        const active = wm.get_active_workspace_index();
        const n = wm.get_n_workspaces();

        for (let i = 0; i < n; i++) {
            const isActive = i === active;
            const dot = new St.Widget({
                width: isActive ? 28 : 18,
                height: 18,
                style: [
                    `background-color: ${isActive ? 'rgba(255,255,255,0.90)' : 'rgba(255,255,255,0.35)'}`,
                    'border-radius: 9px',
                ].join(';'),
                reactive: true,
            });
            const idx = i;
            dot.connect('button-press-event', () => {
                wm.get_workspace_by_index(idx)?.activate(global.get_current_time());
                this._deactivate();
                return Clutter.EVENT_STOP;
            });
            this._switcherBar.add_child(dot);
        }

        Main.uiGroup.add_child(this._switcherBar);

        // Position centred near the bottom
        GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            if (!this._switcherBar) return GLib.SOURCE_REMOVE;
            const w = this._switcherBar.width;
            this._switcherBar.set_position(
                Math.round((global.screen_width - w) / 2),
                global.screen_height - 70,
            );
            return GLib.SOURCE_REMOVE;
        });
    }

    _hideWorkspaceSwitcher() {
        if (this._switcherBar) {
            this._switcherBar.destroy();
            this._switcherBar = null;
        }
    }
}
