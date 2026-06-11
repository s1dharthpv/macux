"""macux-ctl — command-line controller for the MacUX desktop environment.

Commands
--------
  status                    Show daemon and component status
  theme install             Install MacUX theme to user directories
  theme uninstall           Remove MacUX theme from user directories
  theme apply [variant]     Switch theme variant (light|dark|auto)
  theme status              Show current theme and installed state
  config get <key>          Get a config value from the running daemon
  config set <key> <val>    Set a config value in the running daemon
  config list               List all config keys and current values
  restart <component>       Restart a MacUX component
  stop <component>          Stop a MacUX component
  start <component>         Start a MacUX component

Communication
-------------
All daemon commands go through DBus (com.macux.Daemon).
'theme install' runs locally — the daemon does not need to be running.
"""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn


def _error(msg: str) -> NoReturn:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ── DBus helpers ─────────────────────────────────────────────────────────────

def _get_daemon_proxy():
    """Return a dasbus proxy for com.macux.Daemon, or exit with an error."""
    try:
        from dasbus.connection import SessionMessageBus
        bus = SessionMessageBus()
        return bus.get_proxy("com.macux.Daemon", "/com/macux/Daemon")
    except Exception as exc:
        _error(f"Cannot connect to MacUX daemon: {exc}\n"
               "Is macuxd running?  Try: systemctl --user start macux.service")


# ── Subcommand implementations ────────────────────────────────────────────────

def cmd_status(_args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    try:
        version = proxy.GetVersion()
        components = proxy.GetComponents()
        theme = proxy.GetTheme()
    except Exception as exc:
        _error(f"RPC failed: {exc}")

    print(f"MacUX Daemon  v{version}")
    print(f"Theme variant: {theme}")
    print(f"\nComponents ({len(components)}):")
    for name in sorted(components):
        try:
            info = proxy.GetComponentStatus(name)
            pid_str = f"  pid={info['pid']}" if info.get("pid", -1) > 0 else ""
            print(f"  {name:<22} {info['state']:<12}{pid_str}  restarts={info.get('restarts', 0)}")
        except Exception:
            print(f"  {name:<22} (status unavailable)")
    return 0


def cmd_theme_install(args: argparse.Namespace) -> int:
    from themes.theme_installer import ThemeInstaller

    print("Installing MacUX theme...")
    installer = ThemeInstaller()
    result = installer.install()

    if result.success:
        print(f"Done — {len(result.installed_paths)} file(s) written.")
        if args.verbose:
            for p in result.installed_paths:
                print(f"  {p}")
    else:
        print("Installation completed with errors:", file=sys.stderr)
        for err in result.errors:
            print(f"  • {err}", file=sys.stderr)
        return 1
    return 0


def cmd_theme_uninstall(_args: argparse.Namespace) -> int:
    from themes.theme_installer import ThemeInstaller

    print("Removing MacUX theme...")
    ThemeInstaller().uninstall()
    print("Done.")
    return 0


def cmd_theme_apply(args: argparse.Namespace) -> int:
    variant = args.variant
    if variant not in ("light", "dark", "auto"):
        _error(f"Invalid variant {variant!r}. Choose: light | dark | auto")

    proxy = _get_daemon_proxy()
    try:
        proxy.SetTheme(variant)
        print(f"Theme set to: {variant}")
    except Exception as exc:
        _error(f"SetTheme failed: {exc}")
    return 0


def cmd_theme_status(_args: argparse.Namespace) -> int:
    from themes.theme_installer import ThemeInstaller, _GTK4_THEME_DIR, _ICON_THEME_DIR

    installed = _GTK4_THEME_DIR.is_dir()
    icons_installed = _ICON_THEME_DIR.is_dir()

    print(f"GTK4 theme installed : {'yes' if installed else 'no'}  ({_GTK4_THEME_DIR})")
    print(f"Icon theme installed : {'yes' if icons_installed else 'no'}  ({_ICON_THEME_DIR})")

    try:
        proxy = _get_daemon_proxy()
        print(f"Active variant       : {proxy.GetTheme()}")
    except SystemExit:
        print("Active variant       : (daemon not running)")

    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    try:
        value = proxy.GetConfig(args.key)
        print(f"{args.key} = {value!r}")
    except Exception as exc:
        _error(f"GetConfig failed: {exc}")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    # Try to coerce the string value to a Python primitive
    raw = args.value
    value: bool | int | float | str
    if raw.lower() == "true":
        value = True
    elif raw.lower() == "false":
        value = False
    else:
        try:
            value = int(raw)
        except ValueError:
            try:
                value = float(raw)
            except ValueError:
                value = raw

    try:
        proxy.SetConfig(args.key, value)
        print(f"Set {args.key} = {value!r}")
    except Exception as exc:
        _error(f"SetConfig failed: {exc}")
    return 0


def cmd_component_restart(args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    try:
        proxy.RestartComponent(args.component)
        print(f"Restarted: {args.component}")
    except Exception as exc:
        _error(f"RestartComponent failed: {exc}")
    return 0


def cmd_component_stop(args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    try:
        proxy.StopComponent(args.component)
        print(f"Stopped: {args.component}")
    except Exception as exc:
        _error(f"StopComponent failed: {exc}")
    return 0


def cmd_component_start(args: argparse.Namespace) -> int:
    proxy = _get_daemon_proxy()
    try:
        proxy.StartComponent(args.component)
        print(f"Started: {args.component}")
    except Exception as exc:
        _error(f"StartComponent failed: {exc}")
    return 0


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macux-ctl",
        description="MacUX desktop environment controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show daemon and component status")

    # theme
    theme_p = sub.add_parser("theme", help="Theme management")
    theme_sub = theme_p.add_subparsers(dest="theme_command", required=True)

    install_p = theme_sub.add_parser("install", help="Install MacUX theme to user directories")
    install_p.add_argument("-v", "--verbose", action="store_true")

    theme_sub.add_parser("uninstall", help="Remove MacUX theme")

    apply_p = theme_sub.add_parser("apply", help="Switch theme variant")
    apply_p.add_argument("variant", choices=["light", "dark", "auto"])

    theme_sub.add_parser("status", help="Show theme installation state")

    # config
    config_p = sub.add_parser("config", help="Runtime configuration")
    config_sub = config_p.add_subparsers(dest="config_command", required=True)

    get_p = config_sub.add_parser("get", help="Get a config value")
    get_p.add_argument("key", help="Dot-notation key (e.g. dock.icon_size)")

    set_p = config_sub.add_parser("set", help="Set a config value")
    set_p.add_argument("key")
    set_p.add_argument("value")

    # restart / stop / start
    for action in ("restart", "stop", "start"):
        p = sub.add_parser(action, help=f"{action.capitalize()} a component")
        p.add_argument("component", help="Component name (dock, spotlight, …)")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "status": cmd_status,
        "restart": cmd_component_restart,
        "stop": cmd_component_stop,
        "start": cmd_component_start,
    }

    if args.command in dispatch:
        sys.exit(dispatch[args.command](args))
    elif args.command == "theme":
        theme_dispatch = {
            "install": cmd_theme_install,
            "uninstall": cmd_theme_uninstall,
            "apply": cmd_theme_apply,
            "status": cmd_theme_status,
        }
        sys.exit(theme_dispatch[args.theme_command](args))
    elif args.command == "config":
        config_dispatch = {
            "get": cmd_config_get,
            "set": cmd_config_set,
        }
        sys.exit(config_dispatch[args.config_command](args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
