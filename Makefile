# MacUX Makefile — development workflow
# Targets: install, uninstall, test, lint, compile-schemas, deb, clean

PYTHON   := python3
PIP      := pip3
PYTEST   := $(HOME)/.local/bin/pytest
BLACK    := black
RUFF     := ruff
ROOT_DIR := $(shell pwd)

# Paths
SCHEMA_DIR    := gnome-shell/extensions/macux-mission-control@macux/schemas
EXTENSION_DIR := $(HOME)/.local/share/gnome-shell/extensions
SYSTEMD_DIR   := $(HOME)/.config/systemd/user
DESKTOP_DIR   := $(HOME)/.local/share/applications

.PHONY: all install uninstall dev-install test lint format compile-schemas \
        install-extension install-services install-desktop-entries \
        enable-services deb clean help

all: test

# ── Development install ────────────────────────────────────────────────────────

dev-install:
	@echo "Installing MacUX in editable (development) mode..."
	$(PIP) install --user -e ".[dev]"
	$(MAKE) compile-schemas
	$(MAKE) install-extension
	$(MAKE) install-services
	$(MAKE) install-desktop-entries
	@echo "Done. Run 'systemctl --user daemon-reload' to pick up services."

install:
	@echo "Installing MacUX..."
	$(PIP) install --user .
	$(MAKE) compile-schemas
	$(MAKE) install-extension
	$(MAKE) install-services
	$(MAKE) install-desktop-entries
	systemctl --user daemon-reload
	@echo "MacUX installed. Enable services with: make enable-services"

uninstall:
	@echo "Uninstalling MacUX..."
	bash installer/uninstall.sh

# ── GNOME Shell extension ──────────────────────────────────────────────────────

install-extension:
	@echo "Installing GNOME Shell extensions..."
	mkdir -p "$(EXTENSION_DIR)"
	cp -r gnome-shell/extensions/macux-mission-control@macux \
	      "$(EXTENSION_DIR)/macux-mission-control@macux"
	glib-compile-schemas "$(EXTENSION_DIR)/macux-mission-control@macux/schemas/" || true
	cp -r gnome-extensions/macux-shell@macux.com \
	      "$(EXTENSION_DIR)/macux-shell@macux.com"
	glib-compile-schemas "$(EXTENSION_DIR)/macux-shell@macux.com/schemas/" || true
	@echo "Extensions installed. Enable with:"
	@echo "  gnome-extensions enable macux-mission-control@macux"
	@echo "  gnome-extensions enable macux-shell@macux.com"

# ── GSettings schemas ──────────────────────────────────────────────────────────

compile-schemas:
	@echo "Compiling GSettings schemas..."
	glib-compile-schemas $(SCHEMA_DIR)

# ── Systemd user services ──────────────────────────────────────────────────────

install-services:
	@echo "Installing systemd user services..."
	mkdir -p "$(SYSTEMD_DIR)"
	cp installer/systemd/macux.service "$(SYSTEMD_DIR)/"
	cp installer/systemd/macux-spotlight-indexer.service "$(SYSTEMD_DIR)/"
	cp installer/systemd/macux-spotlight-indexer.timer "$(SYSTEMD_DIR)/"
	cp data/systemd/*.service "$(SYSTEMD_DIR)/"

enable-services:
	systemctl --user daemon-reload
	systemctl --user enable --now macux.service
	systemctl --user enable --now macux-dock.service
	systemctl --user enable --now macux-menu-bar.service
	systemctl --user enable --now macux-notification-center.service
	systemctl --user enable --now macux-control-center.service
	systemctl --user enable --now macux-spotlight.service
	systemctl --user enable macux-spotlight-indexer.timer
	systemctl --user start macux-spotlight-indexer.timer

# ── Desktop entries ───────────────────────────────────────────────────────────

install-desktop-entries:
	@echo "Installing desktop entries..."
	mkdir -p "$(DESKTOP_DIR)"
	cp data/applications/*.desktop "$(DESKTOP_DIR)/"
	update-desktop-database -q "$(DESKTOP_DIR)" || true

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/unit/ -v

test-fast:
	$(PYTEST) tests/unit/ -q

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	$(RUFF) check .
	$(PYTHON) -m mypy --ignore-missing-imports .

format:
	$(BLACK) .
	$(RUFF) check --fix .

# ── Debian package ────────────────────────────────────────────────────────────

deb:
	@echo "Building Debian package..."
	cp installer/debian/control debian/control 2>/dev/null || true
	cp installer/debian/changelog debian/changelog 2>/dev/null || true
	cp installer/debian/copyright debian/copyright 2>/dev/null || true
	cp installer/debian/rules debian/rules 2>/dev/null || true
	cp installer/debian/compat debian/compat 2>/dev/null || true
	cp installer/debian/postinst debian/postinst 2>/dev/null || true
	cp installer/debian/prerm debian/prerm 2>/dev/null || true
	dpkg-buildpackage -us -uc -b

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache build/ dist/ *.egg-info/
	rm -f .coverage

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo "MacUX Makefile targets:"
	@echo "  make dev-install       — editable pip install + all assets"
	@echo "  make install           — production install"
	@echo "  make uninstall         — run uninstall.sh"
	@echo "  make test              — run all unit tests"
	@echo "  make lint              — ruff + mypy"
	@echo "  make format            — black + ruff --fix"
	@echo "  make compile-schemas   — glib-compile-schemas"
	@echo "  make install-extension — copy GNOME Shell extension"
	@echo "  make install-services  — copy systemd units"
	@echo "  make enable-services   — enable + start all services"
	@echo "  make deb               — build .deb package"
	@echo "  make clean             — remove build artefacts"
