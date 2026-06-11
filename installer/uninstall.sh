#!/usr/bin/env bash
# MacUX Uninstaller — removes MacUX from Ubuntu 24.04
# Usage: bash uninstall.sh [--purge]  (--purge also removes user config and data)

set -euo pipefail

MACUX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTENSION_DIR="${HOME}/.local/share/gnome-shell/extensions"
CONFIG_DIR="${HOME}/.config/macux"
DATA_DIR="${HOME}/.local/share/macux"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
PURGE=false

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()    { echo -e "${BLUE}[MacUX]${RESET} $*"; }
success() { echo -e "${GREEN}[MacUX] ✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}[MacUX] ⚠${RESET} $*"; }

for arg in "$@"; do
    [[ "$arg" == "--purge" ]] && PURGE=true
done

info "Stopping MacUX services..."
systemctl --user stop macux.service 2>/dev/null || true
systemctl --user stop macux-spotlight-indexer.timer 2>/dev/null || true
systemctl --user disable macux.service 2>/dev/null || true
systemctl --user disable macux-spotlight-indexer.timer 2>/dev/null || true
rm -f "${SYSTEMD_USER_DIR}/macux.service"
rm -f "${SYSTEMD_USER_DIR}/macux-spotlight-indexer.service"
rm -f "${SYSTEMD_USER_DIR}/macux-spotlight-indexer.timer"
systemctl --user daemon-reload
success "Systemd services removed."

info "Disabling GNOME Shell extension..."
gnome-extensions disable macux-shell@macux.com 2>/dev/null || true
rm -rf "${EXTENSION_DIR}/macux-shell@macux.com"
success "GNOME Shell extension removed."

info "Removing Python package..."
pip3.12 uninstall -y macux 2>/dev/null || true
success "Python package removed."

if [[ "$PURGE" == "true" ]]; then
    warn "Purging user config and data..."
    rm -rf "$CONFIG_DIR" "$DATA_DIR"
    success "User config and data purged."
else
    info "User config preserved at ${CONFIG_DIR} (use --purge to remove)"
fi

echo ""
echo -e "${GREEN}MacUX uninstalled. Log out and back in for the menu bar to restore.${RESET}"
