/**
 * MacUX Mission Control — extension preferences page (GNOME 46).
 */

import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences, gettext as _} from
    'resource:///org/gnome/shell/extensions/prefs.js';

export default class MissionControlPrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({
            title: _('Mission Control'),
            icon_name: 'view-grid-symbolic',
        });
        window.add(page);

        // ── Behaviour group ────────────────────────────────────────────────────
        const behaviourGroup = new Adw.PreferencesGroup({
            title: _('Behaviour'),
        });
        page.add(behaviourGroup);

        // Hot corner toggle
        const hotCornerRow = new Adw.SwitchRow({
            title: _('Hot Corner'),
            subtitle: _('Trigger Mission Control by moving the pointer to the top-left corner'),
        });
        settings.bind('hot-corner-enabled', hotCornerRow, 'active',
            Gio.SettingsBindFlags.DEFAULT);
        behaviourGroup.add(hotCornerRow);

        // Window title toggle
        const titlesRow = new Adw.SwitchRow({
            title: _('Show Window Titles'),
            subtitle: _('Display window title beneath each thumbnail'),
        });
        settings.bind('show-window-titles', titlesRow, 'active',
            Gio.SettingsBindFlags.DEFAULT);
        behaviourGroup.add(titlesRow);

        // ── Animation group ────────────────────────────────────────────────────
        const animGroup = new Adw.PreferencesGroup({
            title: _('Animation'),
        });
        page.add(animGroup);

        const durationRow = new Adw.SpinRow({
            title: _('Animation Duration'),
            subtitle: _('Window spread/restore animation in milliseconds'),
            adjustment: new Gtk.Adjustment({
                lower: 0,
                upper: 600,
                step_increment: 10,
            }),
        });
        settings.bind('animation-duration-ms', durationRow, 'value',
            Gio.SettingsBindFlags.DEFAULT);
        animGroup.add(durationRow);

        // ── Keyboard group ─────────────────────────────────────────────────────
        const kbGroup = new Adw.PreferencesGroup({
            title: _('Keyboard'),
            description: _('Edit the toggle shortcut below (default: Super+F3)'),
        });
        page.add(kbGroup);

        const shortcutLabel = new Gtk.Label({
            label: settings.get_strv('toggle-shortcut').join(', ') || _('(none)'),
            halign: Gtk.Align.START,
        });
        const shortcutRow = new Adw.ActionRow({
            title: _('Toggle Shortcut'),
            activatable_widget: shortcutLabel,
        });
        shortcutRow.add_suffix(shortcutLabel);
        kbGroup.add(shortcutRow);
    }
}
