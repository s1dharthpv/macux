/**
 * MacUX DBus Proxy — connects the GNOME Shell extension to the macuxd daemon.
 *
 * Provides typed async wrappers for all com.macux.* interfaces.
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const DAEMON_NAME  = 'com.macux.Daemon';
const DAEMON_PATH  = '/com/macux/Daemon';
const DAEMON_IFACE = `
<node>
  <interface name="com.macux.Daemon">
    <method name="GetVersion"><arg name="version" type="s" direction="out"/></method>
    <method name="Ping"><arg name="pong" type="b" direction="out"/></method>
    <method name="SetTheme"><arg name="theme" type="s" direction="in"/></method>
    <method name="GetTheme"><arg name="theme" type="s" direction="out"/></method>
    <method name="GetConfig">
      <arg name="key" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <signal name="ConfigChanged"><arg name="key" type="s"/><arg name="value" type="v"/></signal>
    <signal name="ThemeChanged"><arg name="theme" type="s"/></signal>
    <signal name="ComponentStateChanged"><arg name="component" type="s"/><arg name="state" type="s"/></signal>
  </interface>
</node>`;

const MacuxDaemonProxy = Gio.DBusProxy.makeProxyWrapper(DAEMON_IFACE);

export class MacuxDBusProxy {
    constructor(extension) {
        this._ext = extension;
        this._proxy = null;
        this._configChangedId = 0;
        this._themeChangedId = 0;
        this._callbacks = { configChanged: [], themeChanged: [] };
    }

    init() {
        try {
            this._proxy = new MacuxDaemonProxy(
                Gio.DBus.session,
                DAEMON_NAME,
                DAEMON_PATH,
                (proxy, error) => {
                    if (error) {
                        console.error('[MacUX DBus] Daemon not available:', error.message);
                        return;
                    }
                    console.log('[MacUX DBus] Connected to macuxd daemon.');
                    this._connectSignals();
                },
                null,
                Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            );
        } catch (e) {
            console.error('[MacUX DBus] Proxy creation failed:', e);
        }
    }

    destroy() {
        if (this._proxy) {
            if (this._configChangedId) {
                this._proxy.disconnectSignal(this._configChangedId);
            }
            if (this._themeChangedId) {
                this._proxy.disconnectSignal(this._themeChangedId);
            }
            this._proxy = null;
        }
    }

    isAvailable() {
        return this._proxy !== null && this._proxy.g_name_owner !== null;
    }

    _connectSignals() {
        this._configChangedId = this._proxy.connectSignal('ConfigChanged', (_proxy, _sender, [key, value]) => {
            this._callbacks.configChanged.forEach(cb => {
                try { cb(key, value); } catch (e) { console.error('[MacUX DBus] ConfigChanged callback:', e); }
            });
        });
        this._themeChangedId = this._proxy.connectSignal('ThemeChanged', (_proxy, _sender, [theme]) => {
            this._callbacks.themeChanged.forEach(cb => {
                try { cb(theme); } catch (e) { console.error('[MacUX DBus] ThemeChanged callback:', e); }
            });
        });
    }

    onConfigChanged(callback) {
        this._callbacks.configChanged.push(callback);
    }

    onThemeChanged(callback) {
        this._callbacks.themeChanged.push(callback);
    }

    async getVersion() {
        if (!this.isAvailable()) return null;
        try {
            const [version] = await this._proxy.GetVersionAsync();
            return version;
        } catch (e) {
            console.error('[MacUX DBus] GetVersion failed:', e);
            return null;
        }
    }

    async getConfig(key) {
        if (!this.isAvailable()) return null;
        try {
            const [value] = await this._proxy.GetConfigAsync(key);
            return value?.unpack?.() ?? value;
        } catch (e) {
            console.error('[MacUX DBus] GetConfig failed for key', key, ':', e);
            return null;
        }
    }

    async setTheme(theme) {
        if (!this.isAvailable()) return;
        try {
            await this._proxy.SetThemeAsync(theme);
        } catch (e) {
            console.error('[MacUX DBus] SetTheme failed:', e);
        }
    }
}
