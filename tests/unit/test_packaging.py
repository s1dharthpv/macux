"""Unit tests for Phase 12 — MacUX Packaging.

Covers:
- version.py: version_tuple, version_string, is_newer, is_compatible, constants
- desktop_entry.py: parse, validate, properties, to_string, load from real files
- manifest.py: InstallEntry, InstallManifest filtering / integrity checks, build_manifest
- schema_compiler.py: list_schemas, validate_schema_dir, schema_ids_from_file, mocked compile
- installer.py: InstallResult, dry-run install/uninstall, check_dependencies (mocked)
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from packaging.version import (
    VERSION,
    VERSION_STRING,
    DEB_VERSION,
    DEB_REVISION,
    RELEASE_NAME,
    version_tuple,
    version_string,
    is_newer,
    is_compatible,
)
from packaging.desktop_entry import DesktopEntry, REQUIRED_FIELDS
from packaging.manifest import InstallEntry, InstallManifest, build_manifest
from packaging.schema_compiler import (
    list_schemas,
    validate_schema_dir,
    schema_ids_from_file,
)
from packaging.installer import InstallResult, install_manifest, uninstall_manifest


# ── version.py ────────────────────────────────────────────────────────────────

class TestVersionConstants:
    def test_version_tuple_type(self):
        assert isinstance(VERSION, tuple)
        assert len(VERSION) == 3

    def test_version_string_matches_tuple(self):
        assert VERSION_STRING == ".".join(str(n) for n in VERSION)

    def test_deb_version_contains_version(self):
        assert VERSION_STRING in DEB_VERSION

    def test_deb_revision_in_deb_version(self):
        assert DEB_REVISION in DEB_VERSION

    def test_release_name_noble(self):
        assert RELEASE_NAME == "noble"


class TestVersionTuple:
    def test_three_part(self):
        assert version_tuple("1.2.3") == (1, 2, 3)

    def test_single_part(self):
        assert version_tuple("5") == (5,)

    def test_two_part(self):
        assert version_tuple("3.4") == (3, 4)

    def test_leading_zeros(self):
        assert version_tuple("1.02.3") == (1, 2, 3)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            version_tuple("1.x.3")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            version_tuple("")

    def test_whitespace_stripped(self):
        assert version_tuple("  1.2.3  ") == (1, 2, 3)


class TestVersionString:
    def test_three_part(self):
        assert version_string((1, 2, 3)) == "1.2.3"

    def test_single_part(self):
        assert version_string((5,)) == "5"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            version_string(())

    def test_roundtrip(self):
        v = "2.10.0"
        assert version_string(version_tuple(v)) == v


class TestIsNewer:
    def test_newer_patch(self):
        assert is_newer("1.0.1", "1.0.0")

    def test_newer_minor(self):
        assert is_newer("1.1.0", "1.0.9")

    def test_newer_major(self):
        assert is_newer("2.0.0", "1.9.9")

    def test_same_is_not_newer(self):
        assert not is_newer("1.0.0", "1.0.0")

    def test_older_is_not_newer(self):
        assert not is_newer("0.9.9", "1.0.0")


class TestIsCompatible:
    def test_exact_match(self):
        assert is_compatible("1.0.0", "1.0.0")

    def test_newer_minor_compatible(self):
        assert is_compatible("1.2.0", "1.0.0")

    def test_different_major_incompatible(self):
        assert not is_compatible("2.0.0", "1.0.0")

    def test_older_minor_incompatible(self):
        assert not is_compatible("1.0.0", "1.1.0")

    def test_newer_patch_compatible(self):
        assert is_compatible("1.0.5", "1.0.0")


# ── desktop_entry.py ──────────────────────────────────────────────────────────

_VALID_DESKTOP = """
[Desktop Entry]
Version=1.0
Type=Application
Name=Test App
Exec=test-app
Icon=test-icon
Comment=A test application
Categories=Utility;
StartupNotify=true
"""

_MISSING_EXEC = """
[Desktop Entry]
Type=Application
Name=No Exec
"""

_MISSING_TYPE = """
[Desktop Entry]
Name=No Type
Exec=cmd
"""

_MISSING_NAME = """
[Desktop Entry]
Type=Application
Exec=cmd
"""

_MULTI_SECTION = """
[Desktop Entry]
Type=Application
Name=With Sections
Exec=test
Icon=icon

[Action new-window]
Name=New Window
Exec=test --new
"""

_COMMENTS_AND_BLANKS = """
# This is a comment
[Desktop Entry]

# Another comment
Type=Application
Name=Test
Exec=cmd
"""


class TestDesktopEntryParse:
    def test_basic_parse(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.name == "Test App"
        assert de.exec_cmd == "test-app"
        assert de.type_ == "Application"
        assert de.icon == "test-icon"
        assert de.comment == "A test application"

    def test_categories(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert "Utility" in de.categories

    def test_startup_notify(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.startup_notify is True

    def test_no_display_default_false(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.no_display is False

    def test_stops_at_second_section(self):
        de = DesktopEntry.parse(_MULTI_SECTION)
        assert de.name == "With Sections"
        assert "New Window" not in de.entries.values()

    def test_comments_ignored(self):
        de = DesktopEntry.parse(_COMMENTS_AND_BLANKS)
        assert de.name == "Test"

    def test_empty_text_returns_empty_entry(self):
        de = DesktopEntry.parse("")
        assert de.entries == {}

    def test_no_desktop_entry_section(self):
        de = DesktopEntry.parse("[Other Section]\nKey=Value\n")
        assert de.entries == {}


class TestDesktopEntryValidate:
    def test_valid_entry_no_errors(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.validate() == []

    def test_missing_exec(self):
        de = DesktopEntry.parse(_MISSING_EXEC)
        errors = de.validate()
        assert any("Exec" in e for e in errors)

    def test_missing_type(self):
        de = DesktopEntry.parse(_MISSING_TYPE)
        errors = de.validate()
        assert any("Type" in e for e in errors)

    def test_missing_name(self):
        de = DesktopEntry.parse(_MISSING_NAME)
        errors = de.validate()
        assert any("Name" in e for e in errors)

    def test_is_valid_true(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.is_valid

    def test_is_valid_false(self):
        de = DesktopEntry.parse(_MISSING_EXEC)
        assert not de.is_valid


class TestDesktopEntryToString:
    def test_roundtrip_contains_entries(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        s = de.to_string()
        assert "[Desktop Entry]" in s
        assert "Name=Test App" in s
        assert "Exec=test-app" in s

    def test_starts_with_header(self):
        de = DesktopEntry.parse(_VALID_DESKTOP)
        assert de.to_string().startswith("[Desktop Entry]")


class TestDesktopEntryLoadRealFiles:
    """Parse the actual .desktop files we ship."""

    _DATA_DIR = Path(__file__).parent.parent.parent / "data" / "applications"

    def _files(self):
        if not self._DATA_DIR.exists():
            pytest.skip("data/applications not found")
        return sorted(self._DATA_DIR.glob("*.desktop"))

    def test_all_files_present(self):
        files = self._files()
        assert len(files) == 8

    def test_all_files_have_required_fields(self):
        for f in self._files():
            de = DesktopEntry.load(f)
            errors = de.validate()
            assert errors == [], f"{f.name}: {errors}"

    def test_all_have_type_application(self):
        for f in self._files():
            de = DesktopEntry.load(f)
            assert de.type_ == "Application", f"{f.name}: Type={de.type_}"

    def test_finder_has_mime_type(self):
        finder_file = self._DATA_DIR / "macux-finder.desktop"
        if not finder_file.exists():
            pytest.skip()
        de = DesktopEntry.load(finder_file)
        assert de.entries.get("MimeType"), "Finder should declare MimeType"

    def test_no_display_components_hidden(self):
        for f in self._files():
            if "finder" in f.name:
                continue  # Finder is user-visible
            de = DesktopEntry.load(f)
            assert de.no_display, f"{f.name} should have NoDisplay=true"


# ── manifest.py ───────────────────────────────────────────────────────────────

class TestInstallEntry:
    def test_dest_dir(self):
        e = InstallEntry(
            source=Path("data/x.desktop"),
            dest=Path("/usr/share/applications/x.desktop"),
        )
        assert e.dest_dir == Path("/usr/share/applications")

    def test_is_executable_644(self):
        e = InstallEntry(source=Path("a"), dest=Path("/b"), mode=0o644)
        assert not e.is_executable()

    def test_is_executable_755(self):
        e = InstallEntry(source=Path("a"), dest=Path("/b"), mode=0o755)
        assert e.is_executable()


class TestInstallManifest:
    def _manifest(self):
        return InstallManifest([
            InstallEntry(Path("data/a.desktop"), Path("/usr/share/applications/a.desktop")),
            InstallEntry(Path("data/b.desktop"), Path("/usr/share/applications/b.desktop")),
            InstallEntry(Path("data/a.service"), Path("/usr/lib/systemd/user/a.service")),
        ])

    def test_len(self):
        assert len(self._manifest()) == 3

    def test_sources(self):
        srcs = self._manifest().sources()
        assert Path("data/a.desktop") in srcs

    def test_dests(self):
        dests = self._manifest().dests()
        assert Path("/usr/share/applications/a.desktop") in dests

    def test_dest_dirs(self):
        dirs = self._manifest().dest_dirs()
        assert Path("/usr/share/applications") in dirs
        assert Path("/usr/lib/systemd/user") in dirs

    def test_no_duplicates(self):
        assert not self._manifest().has_duplicate_dests()

    def test_duplicate_detected(self):
        m = InstallManifest([
            InstallEntry(Path("a"), Path("/same/path")),
            InstallEntry(Path("b"), Path("/same/path")),
        ])
        assert m.has_duplicate_dests()

    def test_filter_by_dest_prefix(self):
        m = self._manifest().filter_by_dest_prefix(Path("/usr/share"))
        assert len(m) == 2
        assert all(str(d).startswith("/usr/share") for d in m.dests())

    def test_filter_by_source_suffix_desktop(self):
        m = self._manifest().filter_by_source_suffix(".desktop")
        assert len(m) == 2

    def test_filter_by_source_suffix_service(self):
        m = self._manifest().filter_by_source_suffix(".service")
        assert len(m) == 1

    def test_missing_sources(self, tmp_path):
        m = InstallManifest([
            InstallEntry(Path("real_file.txt"), Path("/dest")),
            InstallEntry(Path("ghost.txt"), Path("/dest2")),
        ])
        (tmp_path / "real_file.txt").write_text("x")
        missing = m.missing_sources(tmp_path)
        assert Path("ghost.txt") in missing
        assert Path("real_file.txt") not in missing


class TestBuildManifest:
    def test_returns_manifest(self):
        m = build_manifest()
        assert isinstance(m, InstallManifest)
        assert len(m) > 0

    def test_has_desktop_entries(self):
        m = build_manifest()
        desktop = m.filter_by_dest_prefix(Path("/usr/share/applications"))
        assert len(desktop) == 8

    def test_has_systemd_units(self):
        m = build_manifest()
        services = m.filter_by_dest_prefix(Path("/usr/lib/systemd/user"))
        assert len(services) > 0

    def test_has_schema(self):
        m = build_manifest()
        schemas = m.filter_by_dest_prefix(Path("/usr/share/glib-2.0/schemas"))
        assert len(schemas) > 0

    def test_no_duplicate_dests(self):
        m = build_manifest()
        assert not m.has_duplicate_dests()

    def test_all_components_have_service(self):
        m = build_manifest()
        services = m.filter_by_dest_prefix(Path("/usr/lib/systemd/user"))
        service_names = {d.name for d in services.dests()}
        for comp in ["dock", "finder", "launchpad", "menu-bar",
                     "control-center", "notification-center",
                     "mission-control", "spotlight"]:
            assert f"macux-{comp}.service" in service_names, \
                f"Missing service for {comp}"


# ── schema_compiler.py ────────────────────────────────────────────────────────

class TestListSchemas:
    def test_returns_xml_files(self, tmp_path):
        (tmp_path / "a.gschema.xml").write_text("<schema/>")
        (tmp_path / "b.gschema.xml").write_text("<schema/>")
        (tmp_path / "other.txt").write_text("x")
        schemas = list_schemas(tmp_path)
        assert len(schemas) == 2
        assert all(s.suffix == ".xml" for s in schemas)

    def test_empty_dir_returns_empty(self, tmp_path):
        assert list_schemas(tmp_path) == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert list_schemas(tmp_path / "ghost") == []

    def test_sorted_order(self, tmp_path):
        (tmp_path / "z.gschema.xml").write_text("<schema/>")
        (tmp_path / "a.gschema.xml").write_text("<schema/>")
        schemas = list_schemas(tmp_path)
        assert schemas[0].name == "a.gschema.xml"


class TestValidateSchemaDir:
    def test_valid_dir(self, tmp_path):
        (tmp_path / "test.gschema.xml").write_text("<schema/>")
        assert validate_schema_dir(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path):
        errors = validate_schema_dir(tmp_path / "ghost")
        assert any("does not exist" in e for e in errors)

    def test_empty_dir_error(self, tmp_path):
        errors = validate_schema_dir(tmp_path)
        assert any("No .gschema.xml" in e for e in errors)

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        errors = validate_schema_dir(f)
        assert any("Not a directory" in e for e in errors)


class TestSchemaIdsFromFile:
    def test_extracts_id(self, tmp_path):
        f = tmp_path / "test.gschema.xml"
        f.write_text(
            '<schema id="org.gnome.test" path="/org/gnome/test/">\n'
            '</schema>\n'
        )
        ids = schema_ids_from_file(f)
        assert ids == ["org.gnome.test"]

    def test_multiple_schemas(self, tmp_path):
        f = tmp_path / "multi.gschema.xml"
        f.write_text(
            '<schema id="com.a.B" path="/a/">\n'
            '</schema>\n'
            '<schema id="com.a.C" path="/c/">\n'
            '</schema>\n'
        )
        ids = schema_ids_from_file(f)
        assert "com.a.B" in ids
        assert "com.a.C" in ids

    def test_nonexistent_returns_empty(self, tmp_path):
        assert schema_ids_from_file(tmp_path / "ghost.xml") == []

    def test_real_schema_file(self):
        schema = (
            Path(__file__).parent.parent.parent
            / "gnome-shell/extensions/macux-mission-control@macux/schemas"
            / "org.gnome.shell.extensions.macux-mission-control.gschema.xml"
        )
        if not schema.exists():
            pytest.skip("Schema file not found")
        ids = schema_ids_from_file(schema)
        assert any("macux-mission-control" in i for i in ids)


# ── installer.py ─────────────────────────────────────────────────────────────

class TestInstallResult:
    def test_success_when_no_errors(self):
        r = InstallResult(installed=[Path("/a")], errors=[])
        assert r.success is True

    def test_failure_when_errors(self):
        r = InstallResult(errors=["something failed"])
        assert r.success is False

    def test_installed_count(self):
        r = InstallResult(installed=[Path("/a"), Path("/b")])
        assert r.installed_count == 2


class TestInstallManifestDryRun:
    def test_dry_run_no_files_written(self, tmp_path):
        src = tmp_path / "src" / "a.desktop"
        src.parent.mkdir()
        src.write_text("[Desktop Entry]\nType=Application\nName=A\nExec=a\n")
        dest = tmp_path / "dest" / "a.desktop"

        m = InstallManifest([InstallEntry(Path("src/a.desktop"), dest)])
        result = install_manifest(m, project_root=tmp_path, dry_run=True)

        assert result.success
        assert dest in result.installed
        assert not dest.exists()  # dry run: nothing written

    def test_dry_run_reports_all_entries(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        m = InstallManifest([
            InstallEntry(Path("a.txt"), tmp_path / "dest" / "a.txt"),
            InstallEntry(Path("b.txt"), tmp_path / "dest" / "b.txt"),
        ])
        result = install_manifest(m, project_root=tmp_path, dry_run=True)
        assert result.installed_count == 2

    def test_missing_source_recorded_as_error(self, tmp_path):
        m = InstallManifest([
            InstallEntry(Path("ghost.txt"), tmp_path / "dest" / "ghost.txt"),
        ])
        result = install_manifest(m, project_root=tmp_path, dry_run=True)
        assert len(result.errors) == 1

    def test_progress_callback_called(self, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        m = InstallManifest([
            InstallEntry(Path("file.txt"), tmp_path / "dest" / "file.txt"),
        ])
        cb = MagicMock()
        install_manifest(m, project_root=tmp_path, dry_run=True, on_progress=cb)
        cb.assert_called_once()


class TestUninstallManifestDryRun:
    def test_dry_run_lists_would_remove(self, tmp_path):
        f = tmp_path / "installed.txt"
        f.write_text("x")
        m = InstallManifest([InstallEntry(Path("src"), f)])
        result = uninstall_manifest(m, dry_run=True)
        assert f in result.installed
        assert f.exists()  # not actually removed

    def test_nonexistent_goes_to_skipped(self, tmp_path):
        m = InstallManifest([
            InstallEntry(Path("src"), tmp_path / "ghost.txt"),
        ])
        result = uninstall_manifest(m, dry_run=True)
        assert tmp_path / "ghost.txt" in result.skipped


class TestCheckDependencies:
    def test_python3_available(self):
        from packaging.installer import check_dependencies
        deps = check_dependencies()
        assert "python3" in deps
        assert deps["python3"] is True  # python3 must exist in test env

    def test_returns_all_keys(self):
        from packaging.installer import check_dependencies
        deps = check_dependencies()
        assert "glib-compile-schemas" in deps
        assert "gnome-shell" in deps
        assert "systemctl" in deps
