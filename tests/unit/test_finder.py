"""Unit tests for Phase 11 — MacUX Finder.

Covers (all GTK-free):
- FileItem properties: extension, display_size, icon_name, is_hidden
- _guess_mime: extension mapping
- make_file_item: via tmp_path
- sort_items: dirs-first, name/size/modified/kind keys
- DirectoryListing: load, filter_by_name, dirs, files properties
- file_ops: copy_file, move_file, rename_file, delete_file, create_folder, errors
- Bookmark: NamedTuple, path property, display_name
- BookmarkManager: add, remove, contains, all, rename, persistence
- FinderInterface: state machine, callbacks, notify helpers
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import time

from finder.file_model import (
    FileItem,
    DirectoryListing,
    SortKey,
    ViewMode,
    _guess_mime,
    make_file_item,
    sort_items,
)
from finder.file_ops import (
    FileOpsError,
    copy_file,
    create_folder,
    delete_file,
    move_file,
    rename_file,
)
from finder.bookmarks import Bookmark, BookmarkManager


# ── Helpers ────────────────────────────────────────────────────────────────────

def _item(
    name: str = "file.txt",
    size: int = 1024,
    mtime: float = 1_700_000_000.0,
    mime_type: str = "text/plain",
    is_dir: bool = False,
    is_symlink: bool = False,
    is_hidden: bool = False,
    path: Path | None = None,
) -> FileItem:
    p = path or Path(f"/tmp/{name}")
    return FileItem(
        path=p,
        name=name,
        size=size,
        mtime=mtime,
        mime_type=mime_type,
        is_dir=is_dir,
        is_symlink=is_symlink,
        is_hidden=is_hidden,
    )


def _dir_item(name: str = "docs") -> FileItem:
    return _item(name=name, size=0, mime_type="inode/directory", is_dir=True)


# ── FileItem — extension ───────────────────────────────────────────────────────

class TestFileItemExtension:
    def test_txt_extension(self):
        assert _item("readme.txt").extension == "txt"

    def test_py_extension(self):
        assert _item("script.py").extension == "py"

    def test_no_extension(self):
        assert _item("Makefile").extension == ""

    def test_double_extension_last_only(self):
        assert _item("archive.tar.gz").extension == "gz"

    def test_dir_returns_empty(self):
        assert _dir_item("Documents").extension == ""

    def test_hidden_dot_file_no_extension(self):
        assert _item(".bashrc").extension == ""

    def test_uppercase_lowercased(self):
        assert _item("Photo.JPG").extension == "jpg"


# ── FileItem — display_size ────────────────────────────────────────────────────

class TestFileItemDisplaySize:
    def test_dir_returns_dash(self):
        assert _dir_item().display_size == "—"

    def test_bytes(self):
        assert _item(size=512).display_size == "512 B"

    def test_exactly_1023_bytes(self):
        assert _item(size=1023).display_size == "1023 B"

    def test_kilobytes(self):
        assert _item(size=1024).display_size == "1.0 KB"

    def test_megabytes(self):
        assert _item(size=1024 * 1024).display_size == "1.0 MB"

    def test_gigabytes(self):
        assert _item(size=1024 ** 3).display_size == "1.0 GB"

    def test_zero_bytes(self):
        assert _item(size=0).display_size == "0 B"

    def test_fractional_kb(self):
        assert "KB" in _item(size=2048).display_size

    def test_fractional_mb(self):
        assert "MB" in _item(size=2 * 1024 * 1024).display_size


# ── FileItem — icon_name ───────────────────────────────────────────────────────

class TestFileItemIconName:
    def test_folder(self):
        assert _dir_item().icon_name() == "folder-symbolic"

    def test_image_png(self):
        assert _item(mime_type="image/png").icon_name() == "image-x-generic-symbolic"

    def test_image_jpeg(self):
        assert _item(mime_type="image/jpeg").icon_name() == "image-x-generic-symbolic"

    def test_video(self):
        assert _item(mime_type="video/mp4").icon_name() == "video-x-generic-symbolic"

    def test_audio(self):
        assert _item(mime_type="audio/mpeg").icon_name() == "audio-x-generic-symbolic"

    def test_pdf(self):
        assert _item(mime_type="application/pdf").icon_name() == "x-office-document-symbolic"

    def test_text(self):
        assert _item(mime_type="text/plain").icon_name() == "text-x-generic-symbolic"

    def test_zip(self):
        assert _item(mime_type="application/zip").icon_name() == "package-x-generic-symbolic"

    def test_tar(self):
        assert _item(mime_type="application/x-tar").icon_name() == "package-x-generic-symbolic"

    def test_unknown_returns_text(self):
        assert _item(mime_type="application/octet-stream").icon_name() == "text-x-generic-symbolic"


# ── _guess_mime ────────────────────────────────────────────────────────────────

class TestGuessMime:
    def test_directory(self):
        assert _guess_mime(Path("docs"), True) == "inode/directory"

    def test_png(self):
        assert _guess_mime(Path("image.png"), False) == "image/png"

    def test_jpg(self):
        assert _guess_mime(Path("photo.jpg"), False) == "image/jpeg"

    def test_jpeg(self):
        assert _guess_mime(Path("photo.jpeg"), False) == "image/jpeg"

    def test_mp4(self):
        assert _guess_mime(Path("video.mp4"), False) == "video/mp4"

    def test_mp3(self):
        assert _guess_mime(Path("song.mp3"), False) == "audio/mpeg"

    def test_pdf(self):
        assert _guess_mime(Path("doc.pdf"), False) == "application/pdf"

    def test_py(self):
        assert _guess_mime(Path("script.py"), False) == "text/x-python"

    def test_json(self):
        assert _guess_mime(Path("data.json"), False) == "application/json"

    def test_zip(self):
        assert _guess_mime(Path("archive.zip"), False) == "application/zip"

    def test_unknown_extension(self):
        assert _guess_mime(Path("file.xyz"), False) == "application/octet-stream"

    def test_no_extension(self):
        assert _guess_mime(Path("Makefile"), False) == "application/octet-stream"

    def test_case_insensitive_ext(self):
        # _guess_mime lowercases the extension before lookup
        assert _guess_mime(Path("image.PNG"), False) == "image/png"
        assert _guess_mime(Path("video.MP4"), False) == "video/mp4"

    def test_md(self):
        assert _guess_mime(Path("readme.md"), False) == "text/markdown"

    def test_yaml(self):
        assert _guess_mime(Path("config.yaml"), False) == "text/yaml"

    def test_yml(self):
        assert _guess_mime(Path("config.yml"), False) == "text/yaml"


# ── make_file_item ─────────────────────────────────────────────────────────────

class TestMakeFileItem:
    def test_regular_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hi")
        item = make_file_item(f)
        assert item.name == "hello.txt"
        assert item.size == 2
        assert item.mime_type == "text/plain"
        assert not item.is_dir
        assert not item.is_symlink
        assert not item.is_hidden
        assert item.mtime > 0

    def test_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        item = make_file_item(d)
        assert item.is_dir
        assert item.size == 0
        assert item.mime_type == "inode/directory"

    def test_hidden_file(self, tmp_path):
        f = tmp_path / ".hidden"
        f.write_text("x")
        item = make_file_item(f)
        assert item.is_hidden

    def test_uppercase_extension_lowercased(self, tmp_path):
        f = tmp_path / "PHOTO.JPG"
        f.write_text("data")
        item = make_file_item(f)
        assert item.extension == "jpg"
        assert item.mime_type == "image/jpeg"

    def test_nonexistent_path_no_exception(self, tmp_path):
        f = tmp_path / "ghost.txt"
        item = make_file_item(f)
        assert item.size == 0
        assert item.mtime == 0.0

    def test_symlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        item = make_file_item(link)
        assert item.is_symlink


# ── sort_items ─────────────────────────────────────────────────────────────────

class TestSortItems:
    def _mixed(self):
        return [
            _item("b.txt", size=200),
            _dir_item("a_dir"),
            _item("a.txt", size=100),
            _dir_item("b_dir"),
        ]

    def test_dirs_before_files(self):
        items = sort_items(self._mixed(), SortKey.NAME)
        assert all(i.is_dir for i in items[:2])
        assert all(not i.is_dir for i in items[2:])

    def test_sort_by_name_asc(self):
        items = sort_items(self._mixed(), SortKey.NAME, reverse=False)
        dirs = [i for i in items if i.is_dir]
        files = [i for i in items if not i.is_dir]
        assert [d.name for d in dirs] == ["a_dir", "b_dir"]
        assert [f.name for f in files] == ["a.txt", "b.txt"]

    def test_sort_by_name_desc(self):
        items = sort_items(self._mixed(), SortKey.NAME, reverse=True)
        dirs = [i for i in items if i.is_dir]
        assert dirs[0].name == "b_dir"

    def test_sort_by_size(self):
        items = [_item("big.txt", size=500), _item("small.txt", size=10)]
        sorted_items = sort_items(items, SortKey.SIZE)
        assert sorted_items[0].size == 10

    def test_sort_by_mtime(self):
        items = [_item("old.txt", mtime=100.0), _item("new.txt", mtime=999.0)]
        sorted_items = sort_items(items, SortKey.MODIFIED)
        assert sorted_items[0].mtime == 100.0

    def test_sort_by_kind(self):
        items = [_item("z.py", mime_type="text/x-python"),
                 _item("a.txt", mime_type="text/plain")]
        sorted_items = sort_items(items, SortKey.KIND)
        assert sorted_items[0].mime_type == "text/plain"

    def test_empty_list(self):
        assert sort_items([], SortKey.NAME) == []

    def test_only_dirs(self):
        items = [_dir_item("z"), _dir_item("a")]
        sorted_items = sort_items(items, SortKey.NAME)
        assert sorted_items[0].name == "a"


# ── DirectoryListing ───────────────────────────────────────────────────────────

class TestDirectoryListing:
    def test_load_lists_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        listing = DirectoryListing.load(tmp_path)
        assert len(listing) == 2

    def test_hidden_excluded_by_default(self, tmp_path):
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")
        listing = DirectoryListing.load(tmp_path, show_hidden=False)
        names = [i.name for i in listing.items]
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_hidden_included_when_requested(self, tmp_path):
        (tmp_path / ".hidden").write_text("h")
        listing = DirectoryListing.load(tmp_path, show_hidden=True)
        assert any(i.name == ".hidden" for i in listing.items)

    def test_nonexistent_returns_empty(self, tmp_path):
        listing = DirectoryListing.load(tmp_path / "ghost")
        assert len(listing) == 0

    def test_dirs_property(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "file.txt").write_text("x")
        listing = DirectoryListing.load(tmp_path)
        assert all(i.is_dir for i in listing.dirs)
        assert len(listing.dirs) == 1

    def test_files_property(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "file.txt").write_text("x")
        listing = DirectoryListing.load(tmp_path)
        assert all(not i.is_dir for i in listing.files)
        assert len(listing.files) == 1

    def test_filter_by_name_case_insensitive(self, tmp_path):
        (tmp_path / "README.md").write_text("r")
        (tmp_path / "main.py").write_text("m")
        listing = DirectoryListing.load(tmp_path)
        assert len(listing.filter_by_name("readme")) == 1
        assert len(listing.filter_by_name("MAIN")) == 1

    def test_filter_by_name_no_match(self, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        listing = DirectoryListing.load(tmp_path)
        assert listing.filter_by_name("zzz") == []

    def test_sorted_dirs_first(self, tmp_path):
        (tmp_path / "z_file.txt").write_text("z")
        (tmp_path / "a_dir").mkdir()
        listing = DirectoryListing.load(tmp_path)
        assert listing.items[0].is_dir

    def test_len(self, tmp_path):
        for i in range(4):
            (tmp_path / f"file{i}.txt").write_text("x")
        listing = DirectoryListing.load(tmp_path)
        assert len(listing) == 4


# ── file_ops — copy_file ───────────────────────────────────────────────────────

class TestCopyFile:
    def test_basic_copy(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("hello")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        result = copy_file(src, dest_dir)
        assert result == dest_dir / "src.txt"
        assert result.read_text() == "hello"

    def test_source_missing_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="does not exist"):
            copy_file(tmp_path / "ghost.txt", tmp_path)

    def test_dest_not_dir_raises(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        not_a_dir = tmp_path / "not_a_dir.txt"
        not_a_dir.write_text("y")
        with pytest.raises(FileOpsError, match="not a directory"):
            copy_file(src, not_a_dir)

    def test_overwrite_false_raises_on_conflict(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        existing = dest_dir / "src.txt"
        existing.write_text("existing")
        with pytest.raises(FileOpsError, match="already exists"):
            copy_file(src, dest_dir, overwrite=False)

    def test_overwrite_true_replaces(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("new")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        existing = dest_dir / "src.txt"
        existing.write_text("old")
        copy_file(src, dest_dir, overwrite=True)
        assert (dest_dir / "src.txt").read_text() == "new"

    def test_progress_callback_called(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        cb = MagicMock()
        copy_file(src, dest_dir, on_progress=cb)
        cb.assert_called_once_with(1, 1, "src.txt")

    def test_copy_directory(self, tmp_path):
        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "inner.txt").write_text("data")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        result = copy_file(src, dest_dir)
        assert (result / "inner.txt").read_text() == "data"


# ── file_ops — move_file ───────────────────────────────────────────────────────

class TestMoveFile:
    def test_basic_move(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        result = move_file(src, dest_dir)
        assert result.exists()
        assert not src.exists()

    def test_source_missing_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="does not exist"):
            move_file(tmp_path / "ghost.txt", tmp_path)

    def test_dest_not_dir_raises(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        not_dir = tmp_path / "not_dir.txt"
        not_dir.write_text("y")
        with pytest.raises(FileOpsError, match="not a directory"):
            move_file(src, not_dir)

    def test_conflict_raises(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        (dest_dir / "src.txt").write_text("existing")
        with pytest.raises(FileOpsError, match="already exists"):
            move_file(src, dest_dir)


# ── file_ops — rename_file ─────────────────────────────────────────────────────

class TestRenameFile:
    def test_basic_rename(self, tmp_path):
        src = tmp_path / "old.txt"
        src.write_text("data")
        result = rename_file(src, "new.txt")
        assert result.name == "new.txt"
        assert result.read_text() == "data"
        assert not src.exists()

    def test_source_missing_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="does not exist"):
            rename_file(tmp_path / "ghost.txt", "new.txt")

    def test_empty_name_raises(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        with pytest.raises(FileOpsError, match="Invalid name"):
            rename_file(src, "")

    def test_slash_in_name_raises(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        with pytest.raises(FileOpsError, match="Invalid name"):
            rename_file(src, "sub/file.txt")

    def test_dot_raises(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        with pytest.raises(FileOpsError, match="Invalid name"):
            rename_file(src, ".")

    def test_dotdot_raises(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        with pytest.raises(FileOpsError, match="Invalid name"):
            rename_file(src, "..")

    def test_conflict_raises(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("a")
        (tmp_path / "existing.txt").write_text("b")
        with pytest.raises(FileOpsError, match="already exists"):
            rename_file(src, "existing.txt")


# ── file_ops — delete_file ─────────────────────────────────────────────────────

class TestDeleteFile:
    def test_delete_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        delete_file(f)
        assert not f.exists()

    def test_delete_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "inner.txt").write_text("x")
        delete_file(d)
        assert not d.exists()

    def test_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="does not exist"):
            delete_file(tmp_path / "ghost.txt")


# ── file_ops — create_folder ───────────────────────────────────────────────────

class TestCreateFolder:
    def test_basic_create(self, tmp_path):
        result = create_folder(tmp_path, "NewFolder")
        assert result.is_dir()
        assert result.name == "NewFolder"

    def test_parent_not_dir_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(FileOpsError, match="not a directory"):
            create_folder(f, "sub")

    def test_empty_name_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="Invalid folder name"):
            create_folder(tmp_path, "")

    def test_slash_in_name_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="Invalid folder name"):
            create_folder(tmp_path, "a/b")

    def test_already_exists_raises(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        with pytest.raises(FileOpsError, match="Already exists"):
            create_folder(tmp_path, "existing")

    def test_dot_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="Invalid folder name"):
            create_folder(tmp_path, ".")

    def test_dotdot_raises(self, tmp_path):
        with pytest.raises(FileOpsError, match="Invalid folder name"):
            create_folder(tmp_path, "..")


# ── Bookmark ───────────────────────────────────────────────────────────────────

class TestBookmark:
    def test_path_from_file_uri(self):
        bm = Bookmark(uri="file:///home/user/docs", label="")
        assert bm.path == Path("/home/user/docs")

    def test_path_none_for_non_file_uri(self):
        bm = Bookmark(uri="smb://server/share", label="")
        assert bm.path is None

    def test_display_name_uses_label(self):
        bm = Bookmark(uri="file:///home/user/docs", label="My Docs")
        assert bm.display_name == "My Docs"

    def test_display_name_falls_back_to_basename(self):
        bm = Bookmark(uri="file:///home/user/Documents", label="")
        assert bm.display_name == "Documents"

    def test_display_name_root_path(self):
        bm = Bookmark(uri="file:///", label="")
        assert bm.display_name  # non-empty

    def test_display_name_non_file_uri(self):
        bm = Bookmark(uri="smb://server/share", label="")
        assert bm.display_name == "smb://server/share"


# ── BookmarkManager ────────────────────────────────────────────────────────────

class TestBookmarkManager:
    def _mgr(self, tmp_path: Path) -> BookmarkManager:
        return BookmarkManager(path=tmp_path / "bookmarks")

    def test_empty_on_missing_file(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert mgr.all() == []

    def test_add_bookmark(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.add(Path("/home/user/docs"))
        assert mgr.contains(Path("/home/user/docs"))

    def test_add_idempotent(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.add(Path("/home/user/docs"))
        mgr.add(Path("/home/user/docs"))
        assert len(mgr.all()) == 1

    def test_remove_existing(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.add(Path("/home/user/docs"))
        result = mgr.remove(Path("/home/user/docs"))
        assert result is True
        assert not mgr.contains(Path("/home/user/docs"))

    def test_remove_nonexistent_returns_false(self, tmp_path):
        mgr = self._mgr(tmp_path)
        result = mgr.remove(Path("/home/user/docs"))
        assert result is False

    def test_contains_false_for_unknown(self, tmp_path):
        mgr = self._mgr(tmp_path)
        assert not mgr.contains(Path("/nonexistent"))

    def test_persistence(self, tmp_path):
        bm_path = tmp_path / "bookmarks"
        mgr = BookmarkManager(path=bm_path)
        mgr.add(Path("/home/user/docs"), label="Docs")
        mgr.add(Path("/home/user/music"))

        mgr2 = BookmarkManager(path=bm_path)
        assert len(mgr2.all()) == 2
        assert mgr2.contains(Path("/home/user/docs"))
        assert mgr2.contains(Path("/home/user/music"))

    def test_label_persisted(self, tmp_path):
        bm_path = tmp_path / "bookmarks"
        mgr = BookmarkManager(path=bm_path)
        mgr.add(Path("/home/user/docs"), label="My Docs")

        mgr2 = BookmarkManager(path=bm_path)
        bm = next(b for b in mgr2.all() if "docs" in b.uri)
        assert bm.display_name == "My Docs"

    def test_rename_bookmark(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.add(Path("/home/user/docs"), label="Old")
        result = mgr.rename(Path("/home/user/docs"), "New")
        assert result is True
        bm = next(b for b in mgr.all() if "docs" in b.uri)
        assert bm.display_name == "New"

    def test_rename_nonexistent_returns_false(self, tmp_path):
        mgr = self._mgr(tmp_path)
        result = mgr.rename(Path("/nonexistent"), "label")
        assert result is False

    def test_add_removes_order_preserved(self, tmp_path):
        mgr = self._mgr(tmp_path)
        paths = [Path(f"/home/user/dir{i}") for i in range(3)]
        for p in paths:
            mgr.add(p)
        uris = [b.uri for b in mgr.all()]
        assert uris == [f"file://{p}" for p in paths]

    def test_file_format_no_label(self, tmp_path):
        bm_path = tmp_path / "bookmarks"
        mgr = BookmarkManager(path=bm_path)
        mgr.add(Path("/home/user/docs"))
        content = bm_path.read_text()
        assert "file:///home/user/docs" in content
        # Label is empty — line should not have trailing space
        line = [l for l in content.splitlines() if "docs" in l][0]
        assert not line.endswith(" ")

    def test_file_format_with_label(self, tmp_path):
        bm_path = tmp_path / "bookmarks"
        mgr = BookmarkManager(path=bm_path)
        mgr.add(Path("/home/user/docs"), label="My Docs")
        content = bm_path.read_text()
        assert "file:///home/user/docs My Docs" in content

    def test_load_existing_file(self, tmp_path):
        bm_path = tmp_path / "bookmarks"
        bm_path.write_text(
            "file:///home/user/pics\n"
            "file:///home/user/music Custom\n",
            encoding="utf-8",
        )
        mgr = BookmarkManager(path=bm_path)
        items = mgr.all()
        assert len(items) == 2
        assert items[0].uri == "file:///home/user/pics"
        assert items[0].label == ""
        assert items[1].label == "Custom"


# ── FinderInterface ────────────────────────────────────────────────────────────

def _make_finder_iface(open_path_cb=None, reveal_file_cb=None):
    from finder.finder_dbus import FinderInterface
    return FinderInterface(
        open_path_cb=open_path_cb or MagicMock(),
        reveal_file_cb=reveal_file_cb or MagicMock(),
    )


class TestFinderInterface:
    def test_initial_path_empty(self):
        iface = _make_finder_iface()
        assert iface._current_path == ""

    def test_get_current_path_initial(self):
        iface = _make_finder_iface()
        assert str(iface.GetCurrentPath()) == ""

    def test_open_path_sets_current(self):
        iface = _make_finder_iface()
        iface.OpenPath("/home/user/docs")
        assert iface._current_path == "/home/user/docs"

    def test_open_path_calls_callback(self):
        cb = MagicMock()
        iface = _make_finder_iface(open_path_cb=cb)
        iface.OpenPath("/home/user/docs")
        cb.assert_called_once_with("/home/user/docs")

    def test_open_path_updates_get_current(self):
        iface = _make_finder_iface()
        iface.OpenPath("/home/user/music")
        assert str(iface.GetCurrentPath()) == "/home/user/music"

    def test_open_path_successive_calls(self):
        iface = _make_finder_iface()
        iface.OpenPath("/path/one")
        iface.OpenPath("/path/two")
        assert iface._current_path == "/path/two"

    def test_reveal_file_calls_callback(self):
        cb = MagicMock()
        iface = _make_finder_iface(reveal_file_cb=cb)
        iface.RevealFile("/home/user/photo.jpg")
        cb.assert_called_once_with("/home/user/photo.jpg")

    def test_reveal_file_does_not_set_current_path(self):
        iface = _make_finder_iface()
        iface.RevealFile("/home/user/photo.jpg")
        assert iface._current_path == ""

    def test_notify_path_changed_sets_current(self):
        iface = _make_finder_iface()
        iface.notify_path_changed("/home/user/desktop")
        assert iface._current_path == "/home/user/desktop"

    def test_notify_selection_changed_no_exception(self):
        iface = _make_finder_iface()
        iface.notify_selection_changed("/home/user/file.txt")  # must not raise

    def test_open_path_callback_exception_does_not_propagate(self):
        cb = MagicMock(side_effect=RuntimeError("boom"))
        iface = _make_finder_iface(open_path_cb=cb)
        iface.OpenPath("/path")  # must not raise
        assert iface._current_path == "/path"

    def test_reveal_file_callback_exception_does_not_propagate(self):
        cb = MagicMock(side_effect=ValueError("oops"))
        iface = _make_finder_iface(reveal_file_cb=cb)
        iface.RevealFile("/path")  # must not raise

    def test_no_callbacks_no_exception(self):
        from finder.finder_dbus import FinderInterface
        iface = FinderInterface()
        iface.OpenPath("/path")  # must not raise
        iface.RevealFile("/file.txt")  # must not raise

    def test_open_path_empty_string(self):
        iface = _make_finder_iface()
        iface.OpenPath("")
        assert iface._current_path == ""

    def test_full_workflow(self):
        open_cb = MagicMock()
        reveal_cb = MagicMock()
        iface = _make_finder_iface(open_path_cb=open_cb, reveal_file_cb=reveal_cb)

        iface.OpenPath("/home/user")
        iface.RevealFile("/home/user/file.txt")
        iface.notify_path_changed("/home/user/subdir")

        assert iface._current_path == "/home/user/subdir"
        open_cb.assert_called_once_with("/home/user")
        reveal_cb.assert_called_once_with("/home/user/file.txt")
