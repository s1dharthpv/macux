# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""Unit tests for finder.quick_look — GTK-free model layer only.

Covers:
- QuickLookInfo dataclass fields and defaults
- make_quick_look_info: text files, binary files, image-named files,
  missing path, zero-byte files, large text files (> 64 KiB)
- _format_size_human: B / KB / MB / GB boundaries
- MIME + is_text / is_image detection for various extensions
- preview_text truncation and encoding robustness
"""

import tempfile
from pathlib import Path

import pytest

from finder.quick_look import (
    QuickLookInfo,
    _format_size_human,
    _guess_mime,
    make_quick_look_info,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write(directory: str, filename: str, content: bytes) -> Path:
    """Write *content* to *filename* inside *directory* and return the path."""
    p = Path(directory) / filename
    p.write_bytes(content)
    return p


# ── TestSizeHuman ──────────────────────────────────────────────────────────────

class TestSizeHuman:
    """Unit tests for _format_size_human covering all unit boundaries."""

    def test_zero_bytes(self):
        assert _format_size_human(0) == "0 B"

    def test_one_byte(self):
        assert _format_size_human(1) == "1 B"

    def test_1023_bytes(self):
        assert _format_size_human(1_023) == "1023 B"

    def test_exactly_1_kb(self):
        assert _format_size_human(1_024) == "1.0 KB"

    def test_1_5_kb(self):
        assert _format_size_human(int(1.5 * 1_024)) == "1.5 KB"

    def test_just_below_1_mb(self):
        result = _format_size_human(1_024 ** 2 - 1)
        assert result.endswith("KB")

    def test_exactly_1_mb(self):
        assert _format_size_human(1_024 ** 2) == "1.0 MB"

    def test_2_5_mb(self):
        assert _format_size_human(int(2.5 * 1_024 ** 2)) == "2.5 MB"

    def test_just_below_1_gb(self):
        result = _format_size_human(1_024 ** 3 - 1)
        assert result.endswith("MB")

    def test_exactly_1_gb(self):
        assert _format_size_human(1_024 ** 3) == "1.0 GB"

    def test_3_gb(self):
        assert _format_size_human(3 * 1_024 ** 3) == "3.0 GB"


# ── TestMimeDetection ──────────────────────────────────────────────────────────

class TestMimeDetection:
    """Tests for _guess_mime and the resulting is_text / is_image flags."""

    def test_txt_is_text(self):
        assert _guess_mime(Path("note.txt")) == "text/plain"

    def test_py_is_text(self):
        assert _guess_mime(Path("script.py")) == "text/x-python"

    def test_md_is_text(self):
        assert _guess_mime(Path("README.md")) == "text/markdown"

    def test_json_is_not_text_mime(self):
        # application/json — not text/* so is_text would be False
        assert _guess_mime(Path("data.json")) == "application/json"

    def test_png_is_image(self):
        assert _guess_mime(Path("photo.png")) == "image/png"

    def test_jpg_is_image(self):
        assert _guess_mime(Path("photo.jpg")) == "image/jpeg"

    def test_svg_is_image(self):
        assert _guess_mime(Path("icon.svg")) == "image/svg+xml"

    def test_pdf_is_not_text_not_image(self):
        mime = _guess_mime(Path("report.pdf"))
        assert not mime.startswith("text/")
        assert not mime.startswith("image/")

    def test_unknown_extension_octet_stream(self):
        assert _guess_mime(Path("file.xyz")) == "application/octet-stream"

    def test_no_extension_octet_stream(self):
        assert _guess_mime(Path("Makefile")) == "application/octet-stream"

    def test_case_insensitive_extension(self):
        # Path.suffix preserves case; _guess_mime must lower it
        assert _guess_mime(Path("photo.PNG")) == "image/png"
        assert _guess_mime(Path("script.PY")) == "text/x-python"


# ── TestQuickLookInfo ──────────────────────────────────────────────────────────

class TestQuickLookInfo:
    """Integration tests for make_quick_look_info using real temp files."""

    # ── text file ─────────────────────────────────────────────────────────────

    def test_text_file_is_text(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "hello.txt", b"Hello, world!")
            info = make_quick_look_info(p)
            assert info.is_text is True

    def test_text_file_preview_populated(self):
        with tempfile.TemporaryDirectory() as d:
            content = b"Line one\nLine two\n"
            p = _write(d, "sample.txt", content)
            info = make_quick_look_info(p)
            assert info.preview_text is not None
            assert "Line one" in info.preview_text

    def test_text_file_size_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            content = b"abc"
            p = _write(d, "tiny.txt", content)
            info = make_quick_look_info(p)
            assert info.size_bytes == 3

    def test_text_file_size_human(self):
        with tempfile.TemporaryDirectory() as d:
            content = b"x" * 2048
            p = _write(d, "medium.txt", content)
            info = make_quick_look_info(p)
            assert info.size_human == "2.0 KB"

    def test_text_file_no_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "ok.py", b"print('hi')")
            info = make_quick_look_info(p)
            assert info.error is None

    def test_text_file_title_is_filename(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "notes.md", b"# Notes")
            info = make_quick_look_info(p)
            assert info.title == "notes.md"

    # ── binary file ───────────────────────────────────────────────────────────

    def test_binary_file_is_not_text(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "data.bin", bytes(range(256)))
            info = make_quick_look_info(p)
            assert info.is_text is False

    def test_binary_file_no_preview(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "data.bin", bytes(range(256)))
            info = make_quick_look_info(p)
            assert info.preview_text is None

    # ── image-named file ──────────────────────────────────────────────────────

    def test_image_named_file_is_image(self):
        with tempfile.TemporaryDirectory() as d:
            # Content doesn't matter — detection is extension-based
            p = _write(d, "photo.png", b"\x89PNG\r\n\x1a\n")
            info = make_quick_look_info(p)
            assert info.is_image is True

    def test_image_named_file_is_not_text(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "icon.jpg", b"\xff\xd8\xff")
            info = make_quick_look_info(p)
            assert info.is_text is False

    # ── missing path ──────────────────────────────────────────────────────────

    def test_missing_path_has_error(self):
        p = Path("/tmp/__nonexistent_macux_ql_test_file__.txt")
        info = make_quick_look_info(p)
        assert info.error is not None

    def test_missing_path_size_bytes_zero(self):
        p = Path("/tmp/__nonexistent_macux_ql_test_file2__.txt")
        info = make_quick_look_info(p)
        assert info.size_bytes == 0

    def test_missing_path_no_preview(self):
        p = Path("/tmp/__nonexistent_macux_ql_test_file3__.txt")
        info = make_quick_look_info(p)
        assert info.preview_text is None

    # ── zero-byte file ────────────────────────────────────────────────────────

    def test_zero_byte_file_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "empty.txt", b"")
            info = make_quick_look_info(p)
            assert info.size_bytes == 0

    def test_zero_byte_file_size_human(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "empty.txt", b"")
            info = make_quick_look_info(p)
            assert info.size_human == "0 B"

    def test_zero_byte_text_file_preview_is_empty_string(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "empty.txt", b"")
            info = make_quick_look_info(p)
            # Zero bytes: read succeeds, decodes to empty string
            assert info.preview_text == ""

    # ── large text file (> 64 KiB) ────────────────────────────────────────────

    def test_large_text_file_no_preview(self):
        with tempfile.TemporaryDirectory() as d:
            # 65 KiB of text — exceeds the 64 KiB preview threshold
            content = b"a" * (65 * 1_024)
            p = _write(d, "big.txt", content)
            info = make_quick_look_info(p)
            assert info.preview_text is None

    # ── UTF-8 error replacement ────────────────────────────────────────────────

    def test_invalid_utf8_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            # Embed invalid UTF-8 bytes inside valid ASCII text
            content = b"Start\xff\xfeEnd"
            p = _write(d, "messy.txt", content)
            info = make_quick_look_info(p)
            assert info.preview_text is not None
            assert "Start" in info.preview_text
            assert "End" in info.preview_text

    # ── QuickLookInfo path field ───────────────────────────────────────────────

    def test_info_path_matches_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "check.py", b"# hello")
            info = make_quick_look_info(p)
            assert info.path == p

    # ── mime_type field ────────────────────────────────────────────────────────

    def test_mime_type_set_on_info(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "page.html", b"<html></html>")
            info = make_quick_look_info(p)
            assert info.mime_type == "text/html"
