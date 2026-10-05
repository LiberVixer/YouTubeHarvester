import base64
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import warnings
import zipfile

from collect_androidx_published_inputs import collect as collect_published
from collect_androidx_release_sources import collect as collect_trees, version_metadata
from collect_androidx_release_sources import gitiles_json, MODULE_COMMITS, VERSION_COMMITS
from probe_material_icon_sources import compare_icon_source
from probe_androidx_service_sources import compare_aidl, compare_public_r, render_detection
from package_controlled_payloads import digest


class PublishedInputTests(unittest.TestCase):
    def make_inventory(self, root, entries):
        aar = root / "sample.aar"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(aar, "w") as archive:
                for name, data in entries:
                    archive.writestr(name, data)
        inventory = root / "inventory.json"
        inventory.write_text(json.dumps({"artifacts": [{"binary": {
            "file": str(aar), "sha256": digest(aar), "bytes": aar.stat().st_size,
            "module": {"group": "androidx.example", "name": "sample", "version": "1.0"}}}]}))
        return inventory, aar

    def test_exact_resources_and_notices_retained_without_compiled_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = [("res/drawable/icon.png", b"bitmap"), ("assets/data.dat", b"asset"),
                       ("AndroidManifest.xml", b"<manifest/>"), ("proguard.txt", b"-keep class Test"),
                       ("META-INF/NOTICE.txt", b"notice"), ("classes.jar", b"classes"),
                       ("jni/arm64-v8a/native.so", b"ELF"), ("META-INF/module.kotlin_module", b"compiled")]
            inventory, _ = self.make_inventory(root, entries)
            result = collect_published(inventory, root / "out")
            record = result["records"][0]
            self.assertEqual({x["file"] for x in record["retained"]}, {n for n, _ in entries[:5]})
            self.assertEqual(set(record["excludedBinaryOrUnsupported"]), {n for n, _ in entries[5:]})
            for entry in result["files"]:
                path = root / "out" / entry["file"]
                self.assertEqual(digest(path), entry["sha256"])

    def test_changed_artifact_leaves_no_publishable_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, aar = self.make_inventory(root, [("R.txt", b"R")])
            aar.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                collect_published(inventory, root / "out")
            self.assertFalse((root / "out").exists())

    def test_unsafe_and_duplicate_paths_rejected_atomically(self):
        for entries in [[("../escape.txt", b"bad")], [("/escape.txt", b"bad")],
                        [("R.txt", b"first"), ("R.txt", b"second")]]:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inventory, _ = self.make_inventory(root, entries)
                with self.assertRaises(ValueError):
                    collect_published(inventory, root / "out")
                self.assertFalse((root / "out").exists())
                self.assertFalse((root / "escape.txt").exists())

    def test_zip_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = zipfile.ZipInfo("res/link.txt")
            name.create_system = 3
            name.external_attr = (stat.S_IFLNK | 0o777) << 16
            inventory, _ = self.make_inventory(root, [(name, b"../../escape")])
            with self.assertRaisesRegex(ValueError, "symlink"):
                collect_published(inventory, root / "out")
            self.assertFalse((root / "out").exists())

    def test_bounded_uncompressed_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, _ = self.make_inventory(root, [("res/a.txt", b"abcd")])
            with patch("collect_androidx_published_inputs.ENTRY_LIMIT", 3):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    collect_published(inventory, root / "out")
            self.assertFalse((root / "out").exists())

    def test_existing_input_collection_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, _ = self.make_inventory(root, [("R.txt", b"R")])
            output = root / "out"
            collect_published(inventory, output)
            before = digest(output / "ANDROIDX-PUBLISHED-INPUTS.json")
            with self.assertRaisesRegex(ValueError, "new published-input"):
                collect_published(inventory, output)
            self.assertEqual(digest(output / "ANDROIDX-PUBLISHED-INPUTS.json"), before)


class ReleaseTreeTests(unittest.TestCase):
    def test_module_pin_distinguishes_poolingcontainer_from_customview(self):
        pin = MODULE_COMMITS[("androidx.customview", "customview-poolingcontainer", "1.0.0")]
        self.assertNotEqual(pin, VERSION_COMMITS[("customview", "1.0.0")])

    def test_rate_limit_is_retried_but_auth_error_is_not(self):
        limited = HTTPError("url", 429, "Limited", {"Retry-After": "7"}, None)
        with patch("collect_androidx_release_sources.urllib.request.urlopen", side_effect=[
                limited, io.BytesIO(b")]}'{\"entries\": []}")]), \
                patch("collect_androidx_release_sources.time.sleep") as sleep:
            self.assertEqual(gitiles_json("url"), {"entries": []})
        sleep.assert_called_once_with(7)
        with patch("collect_androidx_release_sources.urllib.request.urlopen",
                   side_effect=HTTPError("url", 403, "Denied", {}, None)), \
                patch("collect_androidx_release_sources.time.sleep") as sleep:
            with self.assertRaises(HTTPError):
                gitiles_json("url")
        sleep.assert_not_called()

    def test_historical_missing_version_file_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("collect_androidx_release_sources.urllib.request.urlopen",
                       side_effect=HTTPError("url", 404, "Missing", {}, None)):
                versions, receipt = version_metadata("a" * 40, Path(directory))
            self.assertEqual(versions, {})
            self.assertEqual(receipt["httpStatus"], 404)
            self.assertEqual(receipt["status"], "not-present")

    def test_auth_or_server_error_is_not_treated_as_historical_metadata(self):
        for code in (401, 403, 500):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                with patch("collect_androidx_release_sources.urllib.request.urlopen",
                           side_effect=HTTPError("url", code, "Failure", {}, None)):
                    with self.assertRaises(HTTPError):
                        version_metadata("a" * 40, Path(directory))

    def test_invalid_metadata_is_not_saved(self):
        for data in (b"!not-base64", base64.b64encode(b"[broken TOML")):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with patch("collect_androidx_release_sources.urllib.request.urlopen", return_value=io.BytesIO(data)):
                    with self.assertRaises(ValueError):
                        version_metadata("a" * 40, root)
                self.assertFalse((root / "libraryversions.toml").exists())

    def test_resume_freezes_discovered_commit_and_rechecks_saved_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, output = root / "jvm", root / "out"
            jvm.mkdir()
            module = {"group": "androidx.activity", "name": "activity", "version": "test"}
            source = jvm / "activity-sources.jar"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("Test.kt", b"source")
            (jvm / "JVM-SOURCE-INVENTORY.json").write_text(json.dumps({"artifacts": [{
                "binary": {"module": module}, "downloads": [{"file": source.name, "sha256": digest(source)}]}]}))

            def download_tree(url, target, limit):
                with tarfile.open(target, "w:gz") as archive:
                    member = tarfile.TarInfo("src/Test.kt")
                    member.size = 6
                    archive.addfile(member, io.BytesIO(b"source"))

            with patch("collect_androidx_release_sources.gitiles_json", return_value={
                    "androidx-activity-release": {"value": "a" * 40}}), \
                    patch("collect_androidx_release_sources.download", side_effect=download_tree), \
                    patch("collect_androidx_release_sources.version_metadata", return_value=({}, {"url": "test"})):
                first = collect_trees(jvm, output)
            with patch("collect_androidx_release_sources.gitiles_json", return_value={
                    "androidx-activity-release": {"value": "b" * 40}}), \
                    patch("collect_androidx_release_sources.download") as download, \
                    patch("collect_androidx_release_sources.version_metadata", return_value=({}, {"url": "test"})):
                second = collect_trees(jvm, output, resume=True)
            download.assert_not_called()
            self.assertEqual(second["artifacts"][0]["commit"], "a" * 40)
            self.assertIs(second["completeCorrespondingSourcesVerified"], False)
            (output / first["artifacts"][0]["file"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                collect_trees(jvm, output, resume=True)


class GeneratedSourceTests(unittest.TestCase):
    def test_icons_allow_only_the_initial_build_year(self):
        source = b"/*\n * Copyright 2025 The Android Open Source Project\n */\nfun icon() = 1\n"
        current = source.replace(b"2025", b"2026")
        self.assertEqual(compare_icon_source(source, source), "exact")
        self.assertEqual(compare_icon_source(current, source), "copyright-build-year-only")
        for changed in (current.replace(b"= 1", b"= 2"), b"unexpected\n" + current,
                        current.replace(b"Open Source", b"Changed Source")):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                compare_icon_source(changed, source)

    def test_aidl_allows_only_one_reviewed_command_receipt(self):
        source = (b"/*\n * This file is auto-generated.  DO NOT MODIFY.\n"
                  b" * Using: /linux/36.0.0/aidl --structured --min_sdk_version 23 source.aidl\n"
                  b" */\ninterface Callback {}\n")
        other = source.replace(b"/linux/", b"/darwin/")
        self.assertEqual(compare_aidl(source, other), "exact-except-build-command-receipt")
        for changed in (other.replace(b"Callback", b"Changed"), other.replace(b"36.0.0", b"35.0.0"),
                        other.replace(b" * Using:", b" * Other:"), other.replace(b"version 23", b"version 24")):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                compare_aidl(source, changed)

    def test_public_r_stub_comparison_does_not_ignore_public_code(self):
        prefix = b"public final class R {\n  public static int attr=0;\n"
        actual = prefix + b"  /**\n   * @doconly\n   */\n  public static final class styleable {\n    int hidden;\n  }\n}\n"
        stub = prefix + b"  @android.annotation.DocOnly\n  public static final class styleable {\n  }\n}\n"
        self.assertEqual(compare_public_r(actual, stub), "public-resource-prefix-exact-documentation-stub-tail")
        self.assertEqual(compare_public_r(actual[:-1], stub[:-1]),
                         "public-resource-prefix-exact-documentation-stub-tail")
        for changed in (stub.replace(b"attr=0", b"attr=1"), stub.replace(b" {\n  }", b" {\n    int code;\n  }")):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                compare_public_r(actual, changed)

    def test_unknown_inspection_template_rejected(self):
        with self.assertRaises(ValueError):
            render_detection("unreviewed generator", "androidx.work", "work-runtime")


if __name__ == "__main__":
    unittest.main()
