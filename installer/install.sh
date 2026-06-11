#!/usr/bin/env bash
# MacUX Installer — Ubuntu 24.04
# Usage: bash install.sh [--dev]
# Requires: Ubuntu 24.04, GNOME Shell 46, sudo

set -euo pipefail

MACUX_VERSION="1.0.0"
MACUX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/usr/lib/macux"
EXTENSION_DIR="${HOME}/.local/share/gnome-shell/extensions"
CONFIG_DIR="${HOME}/.config/macux"
DATA_DIR="${HOME}/.local/share/macux"
LOG_DIR="${DATA_DIR}/logs"
DEV_MODE=false

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[MacUX]${RESET} $*"; }
success() { echo -e "${GREEN}[MacUX] ✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}[MacUX] ⚠${RESET} $*"; }
error()   { echo -e "${RED}[MacUX] ✗${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Argument parsing ─────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --dev) DEV_MODE=true ;;
        --help|-h)
            echo "Usage: bash install.sh [--dev]"
            echo "  --dev   Install in development mode (editable pip install)"
            exit 0
            ;;
        *) warn "Unknown argument: $arg" ;;
    esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────────────
check_requirements() {
    info "Checking requirements..."

    # Ubuntu 24.04
    if ! grep -q "Ubuntu 24.04" /etc/os-release 2>/dev/null; then
        warn "MacUX is optimized for Ubuntu 24.04. Proceeding anyway."
    fi

    # GNOME Shell
    if ! command -v gnome-shell &>/dev/null; then
        die "GNOME Shell is not installed. MacUX requires GNOME Shell 46+."
    fi
    local gs_version
    gs_version=$(gnome-shell --version | grep -oP '\d+\.\d+' | head -1)
    local gs_major
    gs_major=$(echo "$gs_version" | cut -d. -f1)
    if [[ "$gs_major" -lt 46 ]]; then
        die "GNOME Shell $gs_version detected. MacUX requires GNOME Shell 46+."
    fi
    success "GNOME Shell $gs_version"

    # Python 3.12+
    if ! python3.12 --version &>/dev/null; then
        die "Python 3.12 is required. Install with: sudo apt install python3.12"
    fi
    success "Python $(python3.12 --version)"

    # GTK4
    if ! python3.12 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" &>/dev/null; then
        die "GTK4 Python bindings missing. Install: sudo apt install python3-gi gir1.2-gtk-4.0"
    fi
    success "GTK4 bindings available"

    # sudo access
    if [[ "$EUID" -eq 0 ]]; then
        die "Do not run this installer as root. It will prompt for sudo when needed."
    fi
}

# ── System package installation ───────────────────────────────────────────────
install_system_packages() {
    info "Installing system dependencies..."
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-4.0 \
        gir1.2-adw-1 \
        gir1.2-gio-2.0 \
        gir1.2-glib-2.0 \
        gir1.2-gdkpixbuf-2.0 \
        gir1.2-nm-1.0 \
        gir1.2-gnomebluetooth-3.0 \
        gir1.2-upower-glib-1.0 \
        libgtk-4-1 \
        libadwaita-1-0 \
        python3-dasbus \
        python3-watchdog \
        python3-pil \
        appmenu-gtk3-module \
        fonts-inter \
        brightnessctl \
        network-manager \
        sqlite3
    success "System packages installed."
}

# ── Python packages ───────────────────────────────────────────────────────────
install_python_packages() {
    info "Installing Python packages..."
    if [[ "$DEV_MODE" == "true" ]]; then
        pip3.12 install --user -e "${MACUX_ROOT}[dev]"
        success "MacUX installed in editable (dev) mode."
    else
        pip3.12 install --user "${MACUX_ROOT}"
        success "MacUX Python packages installed."
    fi
}

# ── Directory setup ───────────────────────────────────────────────────────────
create_directories() {
    info "Creating data directories..."
    mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"
    success "Directories created."
}

# ── Configuration ─────────────────────────────────────────────────────────────
install_default_config() {
    if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
        cp "${MACUX_ROOT}/config/config.toml.default" "${CONFIG_DIR}/config.toml"
        success "Default configuration installed to ${CONFIG_DIR}/config.toml"
    else
        info "User config already exists at ${CONFIG_DIR}/config.toml — skipping."
    fi
}

# ── GNOME Shell extension ─────────────────────────────────────────────────────
install_gnome_extension() {
    info "Installing GNOME Shell extension..."
    local ext_src="${MACUX_ROOT}/gnome-extensions/macux-shell@macux.com"
    local ext_dst="${EXTENSION_DIR}/macux-shell@macux.com"

    mkdir -p "$EXTENSION_DIR"
    rm -rf "$ext_dst"
    cp -r "$ext_src" "$ext_dst"
    success "GNOME Shell extension installed."

    # Compile GSettings schema if present
    if [[ -f "${ext_dst}/schemas/org.gnome.shell.extensions.macux.gschema.xml" ]]; then
        glib-compile-schemas "${ext_dst}/schemas/"
        success "GSettings schema compiled."
    fi

    info "To activate: gnome-extensions enable macux-shell@macux.com"
    info "Or log out and back in, then enable via GNOME Extensions app."
}

# ── Systemd user service ──────────────────────────────────────────────────────
install_systemd_service() {
    info "Installing systemd user service..."
    local systemd_user_dir="${HOME}/.config/systemd/user"
    mkdir -p "$systemd_user_dir"
    cp "${MACUX_ROOT}/installer/systemd/macux.service" "${systemd_user_dir}/"
    cp "${MACUX_ROOT}/installer/systemd/macux-spotlight-indexer.service" "${systemd_user_dir}/"
    cp "${MACUX_ROOT}/installer/systemd/macux-spotlight-indexer.timer" "${systemd_user_dir}/"

    systemctl --user daemon-reload
    systemctl --user enable macux.service
    systemctl --user enable macux-spotlight-indexer.timer
    success "Systemd services installed and enabled."
}

# ── Activation ────────────────────────────────────────────────────────────────
activate() {
    info "Starting MacUX Daemon..."
    systemctl --user start macux.service || warn "Could not start daemon (may need re-login)"

    # Enable GNOME Shell extension
    if command -v gnome-extensions &>/dev/null; then
        gnome-extensions enable macux-shell@macux.com 2>/dev/null || \
            warn "Could not enable extension automatically. Enable manually after login."
    fi
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${GREEN}║     MacUX ${MACUX_VERSION} — Installation Complete   ║${RESET}"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
    echo ""
    echo "  Config:     ${CONFIG_DIR}/config.toml"
    echo "  Data:       ${DATA_DIR}/"
    echo "  Logs:       ${LOG_DIR}/macuxd.log"
    echo "  Extension:  ${EXTENSION_DIR}/macux-shell@macux.com/"
    echo ""
    echo "  Status:     systemctl --user status macux.service"
    echo "  Logs:       journalctl --user -u macux.service -f"
    echo "  Uninstall:  bash ${MACUX_ROOT}/installer/uninstall.sh"
    echo ""
    echo -e "${YELLOW}  → Log out and back in for the GNOME Shell extension to take effect.${RESET}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}"
    echo "  ┌─────────────────────────────────┐"
    echo "  │  MacUX ${MACUX_VERSION} Installer             │"
    echo "  │  macOS-inspired desktop for Ubuntu │"
    echo "  └─────────────────────────────────┘"
    echo -e "${RESET}"

    check_requirements
    install_system_packages
    create_directories
    install_default_config
    install_python_packages
    install_gnome_extension
    install_systemd_service
    activate
    print_summary
}

main "$@"
