# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""Integration tests for the MacUX Finder subsystem.

Tests here exercise the interaction between finder.file_model, finder.file_ops,
and finder.bookmarks using actual temporary filesystem operations.  No GTK or
display connection is required.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from finder.file_model import (
    DirectoryListing,
    FileItem,
    SortKey,
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


# ---------------------------------------------------------------------------
# TestFinderWorkflow — full read/write/delete round-trip
# ---------------------------------------------------------------------------

class TestFinderWorkflow(unittest.TestCase):
    """Full Finder workflow: create files, list directory, delete them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _create_file(self, name: str, content: str = "data") -> Path:
        p = self.root / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_empty_directory_listing_is_empty(self):
        listing = DirectoryListing.load(self.root)
        self.assertEqual(len(listing), 0)

    def test_listing_after_file_creation(self):
        self._create_file("alpha.txt")
        listing = DirectoryListing.load(self.root)
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing.items[0].name, "alpha.txt")

    def test_listing_contains_multiple_files(self):
        for name in ("a.txt", "b.txt", "c.txt"):
            self._create_file(name)
        listing = DirectoryListing.load(self.root)
        self.assertEqual(len(listing), 3)

    def test_listing_sorted_by_name_ascending(self):
        for name in ("zebra.txt", "apple.txt", "mango.txt"):
            self._create_file(name)
        listing = DirectoryListing.load(self.root, sort_key=SortKey.NAME)
        names = [i.name for i in listing.items]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_listing_sorted_by_name_descending(self):
        for name in ("zebra.txt", "apple.txt", "mango.txt"):
            self._create_file(name)
        listing = DirectoryListing.load(
            self.root, sort_key=SortKey.NAME, sort_reverse=True
        )
        names = [i.name for i in listing.items]
        self.assertEqual(names, sorted(names, key=str.lower, reverse=True))

    def test_file_item_properties_from_real_file(self):
        p = self._create_file("report.pdf", content="dummy")
        item = make_file_item(p)
        self.assertEqual(item.name, "report.pdf")
        self.assertEqual(item.extension, "pdf")
        self.assertFalse(item.is_dir)
        self.assertFalse(item.is_hidden)
        self.assertGreater(item.size, 0)

    def test_directory_item_extension_is_empty(self):
        subdir = self.root / "MyFolder"
        subdir.mkdir()
        item = make_file_item(subdir)
        self.assertEqual(item.extension, "")
        self.assertTrue(item.is_dir)

    def test_hidden_file_excluded_by_default(self):
        self._create_file(".hidden")
        self._create_file("visible.txt")
        listing = DirectoryListing.load(self.root, show_hidden=False)
        names = [i.name for i in listing.items]
        self.assertNotIn(".hidden", names)
        self.assertIn("visible.txt", names)

    def test_hidden_file_included_when_requested(self):
        self._create_file(".hidden")
        listing = DirectoryListing.load(self.root, show_hidden=True)
        names = [i.name for i in listing.items]
        self.assertIn(".hidden", names)

    def test_delete_file_removes_it_from_listing(self):
        p = self._create_file("deleteme.txt")
        delete_file(p)
        listing = DirectoryListing.load(self.root)
        names = [i.name for i in listing.items]
        self.assertNotIn("deleteme.txt", names)

    def test_delete_nonexistent_file_raises(self):
        ghost = self.root / "ghost.txt"
        with self.assertRaises(FileOpsError):
            delete_file(ghost)

    def test_create_folder_appears_in_listing(self):
        create_folder(self.root, "NewFolder")
        listing = DirectoryListing.load(self.root)
        names = [i.name for i in listing.items]
        self.assertIn("NewFolder", names)

    def test_create_folder_duplicate_raises(self):
        create_folder(self.root, "DupFolder")
        with self.assertRaises(FileOpsError):
            create_folder(self.root, "DupFolder")

    def test_filter_by_name_returns_matches(self):
        for name in ("notes.txt", "report.pdf", "notebook.md"):
            self._create_file(name)
        listing = DirectoryListing.load(self.root)
        matches = listing.filter_by_name("note")
        match_names = {i.name for i in matches}
        self.assertIn("notes.txt", match_names)
        self.assertIn("notebook.md", match_names)
        self.assertNotIn("report.pdf", match_names)

    def test_dirs_property_returns_only_directories(self):
        (self.root / "subdir").mkdir()
        self._create_file("file.txt")
        listing = DirectoryListing.load(self.root)
        self.assertTrue(all(i.is_dir for i in listing.dirs))

    def test_files_property_returns_only_files(self):
        (self.root / "subdir").mkdir()
        self._create_file("file.txt")
        listing = DirectoryListing.load(self.root)
        self.assertTrue(all(not i.is_dir for i in listing.files))


# ---------------------------------------------------------------------------
# TestCopyMoveRename — file operation interactions
# ---------------------------------------------------------------------------

class TestCopyMoveRename(unittest.TestCase):
    """Verify copy, move, and rename interact correctly with real paths."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src_dir = self.root / "src"
        self.dst_dir = self.root / "dst"
        self.src_dir.mkdir()
        self.dst_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_copy_file_creates_destination(self):
        src = self.src_dir / "hello.txt"
        src.write_text("hello")
        dest = copy_file(src, self.dst_dir)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.name, "hello.txt")

    def test_copy_preserves_source(self):
        src = self.src_dir / "keep.txt"
        src.write_text("keep")
        copy_file(src, self.dst_dir)
        self.assertTrue(src.exists())

    def test_copy_preserves_content(self):
        src = self.src_dir / "content.txt"
        src.write_text("unique content 42")
        dest = copy_file(src, self.dst_dir)
        self.assertEqual(dest.read_text(), "unique content 42")

    def test_copy_without_overwrite_raises_on_conflict(self):
        src = self.src_dir / "dup.txt"
        src.write_text("x")
        copy_file(src, self.dst_dir)
        with self.assertRaises(FileOpsError):
            copy_file(src, self.dst_dir, overwrite=False)

    def test_copy_with_overwrite_succeeds(self):
        src = self.src_dir / "over.txt"
        src.write_text("v1")
        copy_file(src, self.dst_dir)
        src.write_text("v2")
        dest = copy_file(src, self.dst_dir, overwrite=True)
        self.assertEqual(dest.read_text(), "v2")

    def test_move_file_removes_source(self):
        src = self.src_dir / "move_me.txt"
        src.write_text("data")
        move_file(src, self.dst_dir)
        self.assertFalse(src.exists())

    def test_move_file_creates_destination(self):
        src = self.src_dir / "move_me2.txt"
        src.write_text("data")
        dest = move_file(src, self.dst_dir)
        self.assertTrue(dest.exists())

    def test_move_then_move_back(self):
        src = self.src_dir / "bounce.txt"
        src.write_text("bounce")
        moved = move_file(src, self.dst_dir)
        restored = move_file(moved, self.src_dir)
        self.assertTrue(restored.exists())
        self.assertFalse(moved.exists())

    def test_rename_file_new_path_exists(self):
        src = self.src_dir / "old_name.txt"
        src.write_text("x")
        new_path = rename_file(src, "new_name.txt")
        self.assertTrue(new_path.exists())
        self.assertEqual(new_path.name, "new_name.txt")

    def test_rename_file_old_path_gone(self):
        src = self.src_dir / "was_old.txt"
        src.write_text("y")
        rename_file(src, "now_new.txt")
        self.assertFalse(src.exists())

    def test_rename_to_existing_name_raises(self):
        a = self.src_dir / "a.txt"
        b = self.src_dir / "b.txt"
        a.write_text("a")
        b.write_text("b")
        with self.assertRaises(FileOpsError):
            rename_file(a, "b.txt")

    def test_rename_with_invalid_name_raises(self):
        src = self.src_dir / "file.txt"
        src.write_text("z")
        with self.assertRaises(FileOpsError):
            rename_file(src, "bad/name.txt")

    def test_copy_nonexistent_source_raises(self):
        ghost = self.src_dir / "ghost.txt"
        with self.assertRaises(FileOpsError):
            copy_file(ghost, self.dst_dir)

    def test_move_nonexistent_source_raises(self):
        ghost = self.src_dir / "ghost2.txt"
        with self.assertRaises(FileOpsError):
            move_file(ghost, self.dst_dir)


# ---------------------------------------------------------------------------
# TestBookmarkIntegration — bookmarks file round-trip
# ---------------------------------------------------------------------------

class TestBookmarkIntegration(unittest.TestCase):
    """BookmarkManager read/write round-trips against a real temp file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bm_file = Path(self._tmp.name) / "bookmarks"
        self.dir1 = Path(self._tmp.name) / "dir1"
        self.dir2 = Path(self._tmp.name) / "dir2"
        self.dir3 = Path(self._tmp.name) / "dir3"
        for d in (self.dir1, self.dir2, self.dir3):
            d.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _manager(self) -> BookmarkManager:
        return BookmarkManager(path=self.bm_file)

    def test_empty_manager_has_no_bookmarks(self):
        bm = self._manager()
        self.assertEqual(bm.all(), [])

    def test_add_bookmark_persists_to_disk(self):
        bm = self._manager()
        bm.add(self.dir1)
        # Reload from disk
        bm2 = self._manager()
        self.assertTrue(bm2.contains(self.dir1))

    def test_three_bookmark_round_trip(self):
        bm = self._manager()
        bm.add(self.dir1, "First Dir")
        bm.add(self.dir2, "Second Dir")
        bm.add(self.dir3)
        bm2 = self._manager()
        self.assertEqual(len(bm2.all()), 3)

    def test_remove_bookmark_disappears_after_reload(self):
        bm = self._manager()
        bm.add(self.dir1)
        bm.add(self.dir2)
        bm.remove(self.dir1)
        bm2 = self._manager()
        self.assertFalse(bm2.contains(self.dir1))
        self.assertTrue(bm2.contains(self.dir2))

    def test_remove_returns_true_for_existing(self):
        bm = self._manager()
        bm.add(self.dir1)
        self.assertTrue(bm.remove(self.dir1))

    def test_remove_returns_false_for_missing(self):
        bm = self._manager()
        self.assertFalse(bm.remove(self.dir1))

    def test_add_duplicate_is_noop(self):
        bm = self._manager()
        bm.add(self.dir1)
        bm.add(self.dir1)
        self.assertEqual(len(bm.all()), 1)

    def test_bookmark_label_persists(self):
        bm = self._manager()
        bm.add(self.dir1, "My Label")
        bm2 = self._manager()
        found = [b for b in bm2.all() if b.path == self.dir1]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].label, "My Label")

    def test_rename_label_updates_on_disk(self):
        bm = self._manager()
        bm.add(self.dir1, "Old Label")
        bm.rename(self.dir1, "New Label")
        bm2 = self._manager()
        found = [b for b in bm2.all() if b.path == self.dir1]
        self.assertEqual(found[0].label, "New Label")

    def test_rename_nonexistent_returns_false(self):
        bm = self._manager()
        self.assertFalse(bm.rename(self.dir1, "whatever"))

    def test_bookmark_display_name_uses_label(self):
        bm = Bookmark(uri=f"file://{self.dir1}", label="Nice Name")
        self.assertEqual(bm.display_name, "Nice Name")

    def test_bookmark_display_name_falls_back_to_dir_name(self):
        bm = Bookmark(uri=f"file://{self.dir1}", label="")
        self.assertEqual(bm.display_name, self.dir1.name)

    def test_bookmark_path_property_returns_path(self):
        bm = Bookmark(uri=f"file://{self.dir1}", label="")
        self.assertEqual(bm.path, self.dir1)

    def test_bookmark_non_file_uri_path_is_none(self):
        bm = Bookmark(uri="sftp://server/path", label="")
        self.assertIsNone(bm.path)

    def test_contains_returns_false_for_unadded(self):
        bm = self._manager()
        self.assertFalse(bm.contains(self.dir3))

    def test_save_creates_parent_directories(self):
        deep_bm_file = Path(self._tmp.name) / "a" / "b" / "bookmarks"
        bm = BookmarkManager(path=deep_bm_file)
        bm.add(self.dir1)
        self.assertTrue(deep_bm_file.exists())


# ---------------------------------------------------------------------------
# TestDirectoryListingSort — dirs-first invariant across all sort modes
# ---------------------------------------------------------------------------

class TestDirectoryListingSort(unittest.TestCase):
    """Directories always appear before files regardless of sort key."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Create a mix of files and subdirectories
        for name in ("zebra.txt", "apple.py", "mango.md"):
            (self.root / name).write_text("x")
        for name in ("zdir", "adir", "mdir"):
            (self.root / name).mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _listing(self, sort_key: SortKey, reverse: bool = False) -> DirectoryListing:
        return DirectoryListing.load(self.root, sort_key=sort_key, sort_reverse=reverse)

    def _assert_dirs_before_files(self, listing: DirectoryListing) -> None:
        items = listing.items
        dir_indices = [i for i, item in enumerate(items) if item.is_dir]
        file_indices = [i for i, item in enumerate(items) if not item.is_dir]
        if dir_indices and file_indices:
            self.assertLess(
                max(dir_indices),
                min(file_indices),
                msg="Dirs must all appear before any file",
            )

    def test_dirs_first_sort_by_name_asc(self):
        self._assert_dirs_before_files(self._listing(SortKey.NAME))

    def test_dirs_first_sort_by_name_desc(self):
        self._assert_dirs_before_files(self._listing(SortKey.NAME, reverse=True))

    def test_dirs_first_sort_by_size_asc(self):
        self._assert_dirs_before_files(self._listing(SortKey.SIZE))

    def test_dirs_first_sort_by_size_desc(self):
        self._assert_dirs_before_files(self._listing(SortKey.SIZE, reverse=True))

    def test_dirs_first_sort_by_modified_asc(self):
        self._assert_dirs_before_files(self._listing(SortKey.MODIFIED))

    def test_dirs_first_sort_by_modified_desc(self):
        self._assert_dirs_before_files(self._listing(SortKey.MODIFIED, reverse=True))

    def test_dirs_first_sort_by_kind_asc(self):
        self._assert_dirs_before_files(self._listing(SortKey.KIND))

    def test_dirs_first_sort_by_kind_desc(self):
        self._assert_dirs_before_files(self._listing(SortKey.KIND, reverse=True))

    def test_correct_dir_count(self):
        listing = self._listing(SortKey.NAME)
        self.assertEqual(len(listing.dirs), 3)

    def test_correct_file_count(self):
        listing = self._listing(SortKey.NAME)
        self.assertEqual(len(listing.files), 3)

    def test_name_sort_dirs_alphabetical_asc(self):
        listing = self._listing(SortKey.NAME)
        dir_names = [i.name for i in listing.dirs]
        self.assertEqual(dir_names, sorted(dir_names, key=str.lower))

    def test_name_sort_dirs_alphabetical_desc(self):
        listing = self._listing(SortKey.NAME, reverse=True)
        dir_names = [i.name for i in listing.dirs]
        self.assertEqual(dir_names, sorted(dir_names, key=str.lower, reverse=True))

    def test_sort_items_standalone_dirs_before_files(self):
        """sort_items() used standalone also places dirs before files."""
        from finder.file_model import make_file_item
        items = [make_file_item(p) for p in self.root.iterdir()]
        for key in SortKey:
            result = sort_items(items, key)
            dir_indices = [i for i, x in enumerate(result) if x.is_dir]
            file_indices = [i for i, x in enumerate(result) if not x.is_dir]
            if dir_indices and file_indices:
                self.assertLess(max(dir_indices), min(file_indices))


if __name__ == "__main__":
    unittest.main()
