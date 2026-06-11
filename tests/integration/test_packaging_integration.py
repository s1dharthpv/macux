# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""Integration tests for the MacUX packaging subsystem.

Verifies that desktop entry files, the install manifest, version helpers, and
schema utilities all work together correctly.  Every test is self-contained and
produces no side effects on the real filesystem.
"""

import sys
import tempfile
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from packaging.desktop_entry import DesktopEntry, REQUIRED_FIELDS
from packaging.manifest import InstallEntry, InstallManifest, build_manifest
from packaging.schema_compiler import (
    find_compile_tool,
    list_schemas,
    validate_schema_dir,
    schema_ids_from_file,
)
from packaging.version import (
    VERSION,
    VERSION_STRING,
    is_compatible,
    is_newer,
    version_string,
    version_tuple,
)

_APPLICATIONS_DIR = _PROJECT_ROOT / "data" / "applications"
_SCHEMA_DIR = (
    _PROJECT_ROOT
    / "gnome-shell"
    / "extensions"
    / "macux-mission-control@macux"
    / "schemas"
)


# ---------------------------------------------------------------------------
# TestDesktopEntryFiles — parse and validate real .desktop files
# ---------------------------------------------------------------------------

class TestDesktopEntryFiles(unittest.TestCase):
    """Each .desktop file in data/applications/ must be parseable and valid."""

    def _desktop_files(self) -> list[Path]:
        if not _APPLICATIONS_DIR.is_dir():
            self.skipTest(f"applications dir not found: {_APPLICATIONS_DIR}")
        return sorted(_APPLICATIONS_DIR.glob("*.desktop"))

    def test_applications_dir_exists(self):
        self.assertTrue(_APPLICATIONS_DIR.is_dir())

    def test_at_least_one_desktop_file(self):
        files = self._desktop_files()
        self.assertGreater(len(files), 0)

    def test_all_desktop_files_are_valid(self):
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                entry = DesktopEntry.load(path)
                errors = entry.validate()
                self.assertEqual(
                    errors, [], msg=f"{path.name} validation errors: {errors}"
                )

    def test_all_desktop_files_have_name_field(self):
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                entry = DesktopEntry.load(path)
                self.assertTrue(
                    entry.name, msg=f"{path.name} missing Name field"
                )

    def test_all_desktop_files_have_exec_field(self):
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                entry = DesktopEntry.load(path)
                self.assertTrue(
                    entry.exec_cmd, msg=f"{path.name} missing Exec field"
                )

    def test_all_desktop_files_have_type_application(self):
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                entry = DesktopEntry.load(path)
                self.assertEqual(
                    entry.type_, "Application",
                    msg=f"{path.name} expected Type=Application"
                )

    def test_parse_from_string_round_trip(self):
        """Parse → to_string → parse again must produce the same entries."""
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                original = DesktopEntry.load(path)
                text = original.to_string()
                reloaded = DesktopEntry.parse(text)
                self.assertEqual(original.entries, reloaded.entries)

    def test_is_valid_property_matches_validate(self):
        for path in self._desktop_files():
            with self.subTest(file=path.name):
                entry = DesktopEntry.load(path)
                self.assertEqual(entry.is_valid, entry.validate() == [])

    def test_required_fields_constant_is_frozenset(self):
        self.assertIsInstance(REQUIRED_FIELDS, frozenset)

    def test_required_fields_contains_name_type_exec(self):
        self.assertIn("Name", REQUIRED_FIELDS)
        self.assertIn("Type", REQUIRED_FIELDS)
        self.assertIn("Exec", REQUIRED_FIELDS)

    def test_missing_name_produces_validation_error(self):
        text = "[Desktop Entry]\nType=Application\nExec=test\n"
        entry = DesktopEntry.parse(text)
        errors = entry.validate()
        self.assertTrue(any("Name" in e for e in errors))

    def test_missing_exec_produces_validation_error(self):
        text = "[Desktop Entry]\nType=Application\nName=Test\n"
        entry = DesktopEntry.parse(text)
        errors = entry.validate()
        self.assertTrue(any("Exec" in e for e in errors))


# ---------------------------------------------------------------------------
# TestManifestConsistency — build_manifest integrity checks
# ---------------------------------------------------------------------------

class TestManifestConsistency(unittest.TestCase):
    """build_manifest() must produce a well-formed, duplicate-free manifest."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = build_manifest()

    def test_manifest_is_install_manifest_instance(self):
        self.assertIsInstance(self.manifest, InstallManifest)

    def test_manifest_is_non_empty(self):
        self.assertGreater(len(self.manifest), 0)

    def test_no_duplicate_destinations(self):
        self.assertFalse(
            self.manifest.has_duplicate_dests(),
            msg="Manifest contains duplicate destination paths",
        )

    def test_all_destinations_are_absolute(self):
        for entry in self.manifest.entries:
            with self.subTest(dest=entry.dest):
                self.assertTrue(
                    entry.dest.is_absolute(),
                    msg=f"dest {entry.dest} is not absolute",
                )

    def test_all_sources_are_relative(self):
        for entry in self.manifest.entries:
            with self.subTest(source=entry.source):
                self.assertFalse(
                    entry.source.is_absolute(),
                    msg=f"source {entry.source} should be relative",
                )

    def test_desktop_entries_in_manifest(self):
        dests = [str(e.dest) for e in self.manifest.entries]
        self.assertTrue(
            any("applications" in d and ".desktop" in d for d in dests)
        )

    def test_systemd_services_in_manifest(self):
        dests = [str(e.dest) for e in self.manifest.entries]
        self.assertTrue(
            any("systemd" in d and ".service" in d for d in dests)
        )

    def test_filter_by_dest_prefix_returns_subset(self):
        usr_share = Path("/usr/share")
        sub = self.manifest.filter_by_dest_prefix(usr_share)
        self.assertIsInstance(sub, InstallManifest)
        for entry in sub.entries:
            self.assertTrue(str(entry.dest).startswith(str(usr_share)))

    def test_filter_by_source_suffix_desktop(self):
        desktop_sub = self.manifest.filter_by_source_suffix(".desktop")
        for entry in desktop_sub.entries:
            self.assertEqual(entry.source.suffix, ".desktop")

    def test_dest_dirs_returns_set_of_paths(self):
        dirs = self.manifest.dest_dirs()
        self.assertIsInstance(dirs, set)
        self.assertGreater(len(dirs), 0)

    def test_install_entry_mode_default(self):
        entry = InstallEntry(source=Path("src/file.txt"), dest=Path("/usr/share/file.txt"))
        self.assertEqual(entry.mode, 0o644)

    def test_install_entry_is_executable_false_by_default(self):
        entry = InstallEntry(source=Path("src/file.txt"), dest=Path("/usr/share/file.txt"))
        self.assertFalse(entry.is_executable())

    def test_install_entry_is_executable_true_for_0755(self):
        entry = InstallEntry(
            source=Path("src/script.sh"),
            dest=Path("/usr/bin/script"),
            mode=0o755,
        )
        self.assertTrue(entry.is_executable())

    def test_manifest_len_matches_entries_count(self):
        self.assertEqual(len(self.manifest), len(self.manifest.entries))


# ---------------------------------------------------------------------------
# TestVersionCompatibility — end-to-end version comparison scenarios
# ---------------------------------------------------------------------------

class TestVersionCompatibility(unittest.TestCase):
    """Version parsing and comparison helpers work end-to-end."""

    def test_version_tuple_parses_three_part(self):
        self.assertEqual(version_tuple("1.2.3"), (1, 2, 3))

    def test_version_tuple_parses_two_part(self):
        self.assertEqual(version_tuple("2.0"), (2, 0))

    def test_version_tuple_parses_single(self):
        self.assertEqual(version_tuple("5"), (5,))

    def test_version_tuple_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            version_tuple("1.x.3")

    def test_version_string_from_tuple(self):
        self.assertEqual(version_string((1, 2, 3)), "1.2.3")

    def test_version_string_round_trip(self):
        self.assertEqual(version_string(version_tuple(VERSION_STRING)), VERSION_STRING)

    def test_is_newer_returns_true_when_a_newer(self):
        self.assertTrue(is_newer("2.0.0", "1.9.9"))

    def test_is_newer_returns_false_when_equal(self):
        self.assertFalse(is_newer("1.0.0", "1.0.0"))

    def test_is_newer_returns_false_when_a_older(self):
        self.assertFalse(is_newer("1.0.0", "2.0.0"))

    def test_is_newer_minor_bump(self):
        self.assertTrue(is_newer("1.1.0", "1.0.9"))

    def test_is_newer_patch_bump(self):
        self.assertTrue(is_newer("1.0.1", "1.0.0"))

    def test_is_compatible_same_version(self):
        self.assertTrue(is_compatible("1.0.0", "1.0.0"))

    def test_is_compatible_newer_minor_satisfies_older_required(self):
        self.assertTrue(is_compatible("1.2.0", "1.0.0"))

    def test_is_compatible_older_minor_fails(self):
        self.assertFalse(is_compatible("1.0.0", "1.1.0"))

    def test_is_compatible_different_major_fails(self):
        self.assertFalse(is_compatible("2.0.0", "1.0.0"))

    def test_project_version_constant_is_tuple(self):
        self.assertIsInstance(VERSION, tuple)
        self.assertEqual(len(VERSION), 3)

    def test_project_version_string_matches_tuple(self):
        self.assertEqual(VERSION_STRING, version_string(VERSION))


# ---------------------------------------------------------------------------
# TestSchemaDetection — schema utilities return without raising
# ---------------------------------------------------------------------------

class TestSchemaDetection(unittest.TestCase):
    """find_compile_tool(), list_schemas(), validate_schema_dir() don't raise."""

    def test_find_compile_tool_returns_path_or_none(self):
        result = find_compile_tool()
        self.assertTrue(result is None or isinstance(result, str))

    def test_list_schemas_on_real_dir_returns_list(self):
        schemas = list_schemas(_SCHEMA_DIR)
        self.assertIsInstance(schemas, list)

    def test_list_schemas_on_real_dir_at_least_one(self):
        schemas = list_schemas(_SCHEMA_DIR)
        self.assertGreater(
            len(schemas), 0,
            msg=f"Expected at least 1 schema in {_SCHEMA_DIR}",
        )

    def test_list_schemas_returns_paths(self):
        for schema in list_schemas(_SCHEMA_DIR):
            with self.subTest(schema=schema):
                self.assertIsInstance(schema, Path)

    def test_list_schemas_all_have_gschema_xml_suffix(self):
        for schema in list_schemas(_SCHEMA_DIR):
            with self.subTest(schema=schema):
                self.assertTrue(schema.name.endswith(".gschema.xml"))

    def test_list_schemas_on_nonexistent_dir_returns_empty(self):
        result = list_schemas(Path("/nonexistent/path/to/schemas"))
        self.assertEqual(result, [])

    def test_validate_schema_dir_real_dir_no_errors(self):
        errors = validate_schema_dir(_SCHEMA_DIR)
        self.assertEqual(errors, [], msg=f"Schema validation errors: {errors}")

    def test_validate_schema_dir_nonexistent_returns_errors(self):
        errors = validate_schema_dir(Path("/nonexistent/schema/dir"))
        self.assertGreater(len(errors), 0)

    def test_schema_ids_from_file_returns_list(self):
        schemas = list_schemas(_SCHEMA_DIR)
        if not schemas:
            self.skipTest("No schema files found")
        ids = schema_ids_from_file(schemas[0])
        self.assertIsInstance(ids, list)

    def test_schema_ids_from_file_at_least_one_id(self):
        schemas = list_schemas(_SCHEMA_DIR)
        if not schemas:
            self.skipTest("No schema files found")
        ids = schema_ids_from_file(schemas[0])
        self.assertGreater(len(ids), 0)

    def test_schema_ids_are_dot_namespaced_strings(self):
        schemas = list_schemas(_SCHEMA_DIR)
        if not schemas:
            self.skipTest("No schema files found")
        for schema_id in schema_ids_from_file(schemas[0]):
            with self.subTest(id=schema_id):
                self.assertIn(".", schema_id)

    def test_schema_ids_from_nonexistent_file_returns_empty(self):
        result = schema_ids_from_file(Path("/nonexistent/schema.gschema.xml"))
        self.assertEqual(result, [])

    def test_validate_schema_dir_with_temp_empty_dir_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            errors = validate_schema_dir(Path(td))
            self.assertGreater(len(errors), 0)

    def test_validate_schema_dir_with_temp_dir_having_schema(self):
        with tempfile.TemporaryDirectory() as td:
            schema = Path(td) / "org.test.app.gschema.xml"
            schema.write_text(
                '<schemalist><schema id="org.test.app" path="/org/test/app/"/>'
                "</schemalist>\n"
            )
            errors = validate_schema_dir(Path(td))
            self.assertEqual(errors, [])

    def test_list_schemas_in_temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "foo.gschema.xml").write_text("<schemalist/>")
            (root / "bar.gschema.xml").write_text("<schemalist/>")
            (root / "ignore.txt").write_text("not a schema")
            schemas = list_schemas(root)
            names = {s.name for s in schemas}
            self.assertIn("foo.gschema.xml", names)
            self.assertIn("bar.gschema.xml", names)
            self.assertNotIn("ignore.txt", names)


if __name__ == "__main__":
    unittest.main()
