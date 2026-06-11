# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""MacUX Finder — Space-bar Quick Look file preview.

Architecture
------------
- Pure model layer (``QuickLookInfo`` + helpers) has zero GTK dependency and
  can be unit-tested without a display server.
- GTK/Libadwaita layer (``QuickLookWindow``) is imported lazily so that the
  model can be used in headless contexts.
"""

from dataclasses import dataclass
from pathlib import Path


# ── MIME lookup table (shared subset from file_model) ─────────────────────────

_MIME_MAP: dict[str, str] = {
    # images
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
    "heic": "image/heic", "bmp": "image/bmp", "tiff": "image/tiff",
    "tif": "image/tiff", "ico": "image/x-icon",
    # video
    "mp4": "video/mp4", "mkv": "video/x-matroska", "avi": "video/x-msvideo",
    "mov": "video/quicktime", "webm": "video/webm", "flv": "video/x-flv",
    # audio
    "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg",
    "wav": "audio/wav", "aac": "audio/aac", "m4a": "audio/mp4",
    "opus": "audio/opus",
    # documents / text
    "pdf": "application/pdf",
    "txt": "text/plain", "md": "text/markdown", "rst": "text/x-rst",
    "html": "text/html", "htm": "text/html",
    "css": "text/css", "js": "text/javascript",
    "py": "text/x-python", "sh": "text/x-shellscript",
    "json": "application/json", "xml": "text/xml",
    "yaml": "text/yaml", "yml": "text/yaml",
    "csv": "text/csv", "tsv": "text/tab-separated-values",
    "c": "text/x-c", "h": "text/x-c", "cpp": "text/x-c++",
    "rs": "text/x-rust", "go": "text/x-go",
    "ts": "text/typescript", "tsx": "text/typescript",
    "jsx": "text/javascript", "rb": "text/x-ruby",
    "java": "text/x-java", "kt": "text/x-kotlin",
    "swift": "text/x-swift", "toml": "text/x-toml",
    "ini": "text/x-ini", "cfg": "text/x-ini",
    # archives
    "zip": "application/zip", "tar": "application/x-tar",
    "gz": "application/x-gzip", "bz2": "application/x-bzip2",
    "xz": "application/x-xz", "7z": "application/x-7z-compressed",
    "rar": "application/x-rar",
}

_TEXT_PREVIEW_LIMIT = 64 * 1024   # 64 KiB — files larger than this skip text preview
_TEXT_PREVIEW_BYTES = 4096        # bytes to actually read for the preview snippet


def _guess_mime(path: Path) -> str:
    """Return a MIME type string derived from *path*'s extension."""
    ext = path.suffix.lstrip(".").lower()
    return _MIME_MAP.get(ext, "application/octet-stream")


def _format_size_human(size_bytes: int) -> str:
    """Format *size_bytes* as a human-readable string (1-decimal precision)."""
    if size_bytes < 1_024:
        return f"{size_bytes} B"
    if size_bytes < 1_024 ** 2:
        return f"{size_bytes / 1_024:.1f} KB"
    if size_bytes < 1_024 ** 3:
        return f"{size_bytes / 1_024 ** 2:.1f} MB"
    return f"{size_bytes / 1_024 ** 3:.1f} GB"


def _icon_name_for_mime(mime_type: str) -> str:
    """Map a MIME type to a symbolic icon name."""
    if mime_type.startswith("image/"):
        return "image-x-generic-symbolic"
    if mime_type.startswith("video/"):
        return "video-x-generic-symbolic"
    if mime_type.startswith("audio/"):
        return "audio-x-generic-symbolic"
    if mime_type == "application/pdf":
        return "x-office-document-symbolic"
    if mime_type.startswith("text/"):
        return "text-x-generic-symbolic"
    if mime_type in (
        "application/zip", "application/x-tar", "application/x-gzip",
        "application/x-bzip2", "application/x-xz",
        "application/x-7z-compressed", "application/x-rar",
    ):
        return "package-x-generic-symbolic"
    return "text-x-generic-symbolic"


# ── Pure model ─────────────────────────────────────────────────────────────────

@dataclass
class QuickLookInfo:
    """Snapshot of a file's metadata + optional preview content.

    All fields are plain Python — no GTK dependency.
    """

    path: Path
    title: str               # display name (filename)
    mime_type: str
    size_bytes: int
    size_human: str
    is_text: bool
    is_image: bool
    preview_text: str | None   # first ~4 KiB of text, or None
    error: str | None          # set if stat/read failed


def make_quick_look_info(path: Path) -> QuickLookInfo:
    """Build a :class:`QuickLookInfo` by inspecting *path* on disk.

    Never raises — errors are recorded in ``QuickLookInfo.error``.
    """
    title = path.name

    # ── stat ──────────────────────────────────────────────────────────────────
    try:
        st = path.stat()
        size_bytes = st.st_size
    except OSError as exc:
        return QuickLookInfo(
            path=path,
            title=title,
            mime_type="application/octet-stream",
            size_bytes=0,
            size_human="0 B",
            is_text=False,
            is_image=False,
            preview_text=None,
            error=str(exc),
        )

    mime_type = _guess_mime(path)
    is_text = mime_type.startswith("text/")
    is_image = mime_type.startswith("image/")
    size_human = _format_size_human(size_bytes)

    # ── text preview ──────────────────────────────────────────────────────────
    preview_text: str | None = None
    if is_text and size_bytes <= _TEXT_PREVIEW_LIMIT:
        try:
            raw = path.read_bytes()[:_TEXT_PREVIEW_BYTES]
            preview_text = raw.decode("utf-8", errors="replace")
        except OSError:
            pass  # leave preview_text as None

    return QuickLookInfo(
        path=path,
        title=title,
        mime_type=mime_type,
        size_bytes=size_bytes,
        size_human=size_human,
        is_text=is_text,
        is_image=is_image,
        preview_text=preview_text,
        error=None,
    )


# ── GTK / Libadwaita layer ────────────────────────────────────────────────────

def _build_gtk_window(info: QuickLookInfo, on_close=None):  # type: ignore[return]
    """Construct and return a ``QuickLookWindow`` for *info*.

    Importing this function triggers GTK initialisation; keep it separate so
    the model layer remains importable without a display.
    """
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk  # noqa: PLC0415

    # ── Window ────────────────────────────────────────────────────────────────

    class QuickLookWindow(Adw.Window):
        """Floating preview window triggered by Space in the Finder."""

        def __init__(self, ql_info: QuickLookInfo, _on_close=None) -> None:
            super().__init__()

            self._on_close = _on_close

            # ── geometry ──────────────────────────────────────────────────────
            self.set_default_size(680, 480)
            self.set_resizable(False)
            self.add_css_class("macux-quick-look")

            # ── keyboard shortcut: Escape → close ─────────────────────────────
            esc_ctrl = Gtk.ShortcutController()
            esc_ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
            shortcut = Gtk.Shortcut.new(
                Gtk.KeyvalTrigger.new(
                    ord("Escape") if hasattr(Gtk, "KEY_Escape") else 0xFF1B,
                    0,
                ),
                Gtk.CallbackAction.new(self._on_escape),
            )
            esc_ctrl.add_shortcut(shortcut)
            self.add_controller(esc_ctrl)

            # ── window close signal ───────────────────────────────────────────
            self.connect("close-request", self._handle_close)

            # ── layout ────────────────────────────────────────────────────────
            toolbar_view = Adw.ToolbarView()
            self.set_content(toolbar_view)

            header = Adw.HeaderBar()
            header.set_title_widget(self._build_title_widget(ql_info))
            toolbar_view.add_top_bar(header)

            content = self._build_content(ql_info)
            toolbar_view.set_content(content)

        # ── title bar ─────────────────────────────────────────────────────────

        def _build_title_widget(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            box.set_valign(Gtk.Align.CENTER)

            name_label = Gtk.Label(label=ql_info.title)
            name_label.add_css_class("title-4")
            box.append(name_label)

            size_label = Gtk.Label(label=ql_info.size_human)
            size_label.add_css_class("caption")
            size_label.add_css_class("dim-label")
            box.append(size_label)

            return box

        # ── content area ──────────────────────────────────────────────────────

        def _build_content(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            if ql_info.error is not None:
                return self._build_error_view(ql_info)
            if ql_info.is_text:
                return self._build_text_view(ql_info)
            if ql_info.is_image:
                return self._build_image_view(ql_info)
            return self._build_generic_view(ql_info)

        def _build_text_view(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            scroll = Gtk.ScrolledWindow()
            scroll.set_hexpand(True)
            scroll.set_vexpand(True)

            text_view = Gtk.TextView()
            text_view.set_editable(False)
            text_view.set_cursor_visible(False)
            text_view.set_monospace(True)
            text_view.set_left_margin(12)
            text_view.set_right_margin(12)
            text_view.set_top_margin(8)
            text_view.set_bottom_margin(8)

            if ql_info.preview_text is not None:
                text_view.get_buffer().set_text(ql_info.preview_text)
            else:
                placeholder = (
                    f"(File is too large to preview — {ql_info.size_human})"
                )
                text_view.get_buffer().set_text(placeholder)

            scroll.set_child(text_view)
            return scroll

        def _build_image_view(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            scroll = Gtk.ScrolledWindow()
            scroll.set_hexpand(True)
            scroll.set_vexpand(True)

            picture = Gtk.Picture()
            picture.set_hexpand(True)
            picture.set_vexpand(True)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)

            if ql_info.path.exists():
                picture.set_filename(str(ql_info.path))

            scroll.set_child(picture)
            return scroll

        def _build_generic_view(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            box.set_hexpand(True)
            box.set_vexpand(True)

            icon = Gtk.Image.new_from_icon_name(
                _icon_name_for_mime(ql_info.mime_type)
            )
            icon.set_pixel_size(96)
            box.append(icon)

            name_label = Gtk.Label(label=ql_info.title)
            name_label.add_css_class("title-2")
            box.append(name_label)

            size_label = Gtk.Label(label=ql_info.size_human)
            size_label.add_css_class("body")
            size_label.add_css_class("dim-label")
            box.append(size_label)

            mime_label = Gtk.Label(label=ql_info.mime_type)
            mime_label.add_css_class("caption")
            mime_label.add_css_class("dim-label")
            box.append(mime_label)

            return box

        def _build_error_view(self, ql_info: QuickLookInfo) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            box.set_hexpand(True)
            box.set_vexpand(True)

            icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
            icon.set_pixel_size(64)
            box.append(icon)

            label = Gtk.Label(label=ql_info.error or "Unknown error")
            label.add_css_class("body")
            label.set_wrap(True)
            box.append(label)

            return box

        # ── callbacks ─────────────────────────────────────────────────────────

        def _on_escape(self, _widget, _args) -> bool:
            self.close()
            return True

        def _handle_close(self, _window) -> bool:
            if self._on_close is not None:
                self._on_close()
            return False  # allow default close behaviour

    return QuickLookWindow(info, on_close)


def show_quick_look(path: Path, parent=None) -> object | None:
    """Create and present a :class:`QuickLookWindow` for *path*.

    Returns the window object, or ``None`` if *path* does not exist.
    ``parent`` is an optional transient-parent window (unused if GTK is not
    available, kept for forward-compatibility).
    """
    if not path.exists():
        return None

    info = make_quick_look_info(path)
    window = _build_gtk_window(info)

    if parent is not None:
        try:
            window.set_transient_for(parent)
        except Exception:
            pass

    window.present()
    return window
