import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from package_release import ABIS, check_apk_abi, check_source_review, digest, main, package_original_notices


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        source = self.folder / "source.txt"
        source.write_text("source")
        self.archive = self.folder / "sources.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(source, arcname="source.txt")
            archive.add(source, arcname="source-notice-audit/notices/example/LICENSE")
        self.apks = {}
        for abi in ABIS:
            apk = self.folder / (abi + ".apk")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/" + abi + "/native.so", abi.encode())
            self.apks[abi] = apk
        self.commit = "a" * 40
        self.review = {"schemaVersion": 1, "completeCorrespondingSourcesVerified": True,
                       "remaining": [], "releaseCommit": self.commit,
                       "sourceArchiveSha256": digest(self.archive),
                       "apkSha256": {abi: digest(apk) for abi, apk in self.apks.items()}}
        self.path = self.folder / "review.json"

    def check(self):
        self.path.write_text(json.dumps(self.review))
        return check_source_review(self.archive, self.path, self.commit, self.apks)

    def test_exact_completed_review(self):
        self.assertEqual(self.check(), self.review)

    def test_preparation_and_truthy_flags_are_rejected(self):
        for flag in (False, "true", 1, None):
            with self.subTest(flag=flag):
                self.review["completeCorrespondingSourcesVerified"] = flag
                with self.assertRaises(ValueError):
                    self.check()

    def test_unresolved_gate_is_rejected(self):
        self.review["remaining"] = ["Missing build inputs"]
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_release_commit(self):
        self.review["releaseCommit"] = "b" * 40
        with self.assertRaises(ValueError):
            self.check()

    def test_changed_archive(self):
        with self.archive.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(ValueError):
            self.check()

    def test_changed_candidate(self):
        self.apks["x86"].write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.check()

    def test_all_four_abis_required(self):
        self.apks.pop("x86")
        self.review["apkSha256"].pop("x86")
        with self.assertRaises(ValueError):
            self.check()

    def test_native_abi_must_match_the_selected_candidate(self):
        check_apk_abi(self.apks["x86"], "x86")
        with self.assertRaises(ValueError):
            check_apk_abi(self.apks["x86"], "x86_64")
        with zipfile.ZipFile(self.apks["x86"], "a") as archive:
            archive.writestr("lib/x86_64/native.so", b"extra ABI")
        with self.assertRaises(ValueError):
            check_apk_abi(self.apks["x86"], "x86")

    def test_empty_archive_rejected_even_with_matching_hash(self):
        with tarfile.open(self.archive, "w:gz"):
            pass
        self.review["sourceArchiveSha256"] = digest(self.archive)
        with self.assertRaises(ValueError):
            self.check()

    def test_original_notices_keep_exact_bytes(self):
        output = self.folder / "notices.zip"
        result = package_original_notices(self.archive, output)
        self.assertEqual(result["files"], 1)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("source-notice-audit/notices/example/LICENSE"), b"source")

    def test_missing_or_escaping_original_notices_are_rejected(self):
        for name in ("source.txt", "source-notice-audit/notices/../../escape"):
            with self.subTest(name=name):
                archive_path = self.folder / "invalid.tar.gz"
                with tarfile.open(archive_path, "w:gz") as archive:
                    member = tarfile.TarInfo(name)
                    member.size = 6
                    archive.addfile(member, io.BytesIO(b"source"))
                output = self.folder / (str(len(name)) + ".zip")
                with self.assertRaises(ValueError):
                    package_original_notices(archive_path, output)

    def run_packager(self, failure=None):
        android = self.folder / "android"
        (android / "app").mkdir(parents=True)
        (android / "app/build.gradle.kts").write_text('versionName = "1.2.1"\nversionCode = 120100\n')
        (android / "LICENSE").write_text("approved")
        (android / "NOTICE").write_text("third-party notices")
        (android / "runtime.properties").write_text("version=1\n")
        sdk = self.folder / "sdk"
        tools = sdk / "build-tools/36.0.0"
        tools.mkdir(parents=True)
        (tools / "apksigner").touch()
        candidates = self.folder / "candidates"
        candidates.mkdir()
        for abi, apk in self.apks.items():
            target = candidates / ("YouTubeHarvester-1.2.1-" + abi + "-release.apk")
            target.write_bytes(apk.read_bytes())
        output = self.folder / "dist"
        self.path.write_text(json.dumps(self.review))
        def git(args, **kwargs):
            if args[1] == "rev-parse":
                return self.commit + "\n"
            if args[1] == "status":
                return b""
            raise AssertionError(args)
        def archive(args, **kwargs):
            name = next(arg.removeprefix("--output=") for arg in args if arg.startswith("--output="))
            Path(name).write_bytes(b"committed application source")
            return subprocess.CompletedProcess(args, 0)
        calls = []
        def signature(apk, *args):
            calls.append(apk)
            if failure == "signature" and len(calls) == 3:
                raise ValueError("signature mismatch")
            return {"apk": apk.name}
        argv = ["package_release.py", "--tag", "android-v1.2.1", "--sources", str(self.archive),
                "--review", str(self.path), "--candidate-dir", str(candidates), "--output", str(output)]
        with patch("package_release.__file__", str(android / "scripts/package_release.py")), patch.object(
                sys, "argv", argv), patch.dict(os.environ, {"ANDROID_HOME": str(sdk),
                "YTH_ANDROID_CERT_SHA256": "0" * 64}), patch(
                "package_release.subprocess.check_output", side_effect=git), patch(
                "package_release.subprocess.run", side_effect=archive), patch(
                "package_release.verify", side_effect=signature), patch("sys.stdout", new=io.StringIO()):
            if failure:
                with self.assertRaises(ValueError):
                    main()
            else:
                main()
        return output, candidates, calls

    def test_packages_preserved_signed_candidates_atomically(self):
        output, candidates, calls = self.run_packager()
        self.assertEqual(len(calls), 4)
        self.assertTrue(json.loads((output / "BUILD-INFO-android.json").read_text())["reusedSignedCandidates"])
        for abi in ABIS:
            name = "YouTubeHarvester-1.2.1-" + abi + "-release.apk"
            self.assertEqual(digest(output / name), self.review["apkSha256"][abi])
            self.assertEqual(digest(candidates / name), self.review["apkSha256"][abi])
        self.assertEqual((output / "LICENSE-android.txt").read_text(), "approved")
        self.assertEqual((output / "NOTICE-android.txt").read_text(), "third-party notices")
        self.assertEqual(json.loads((output / "BUILD-INFO-android.json").read_text())["originalNotices"]["files"], 1)
        checksums = (output / "SHA256SUMS-android.txt").read_text()
        for name in ("LICENSE-android.txt", "NOTICE-android.txt"):
            self.assertIn(f"{digest(output / name)}  {name}\n", checksums)
        self.assertFalse(list(self.folder.glob("yth-release-*")))

    def test_signature_failure_leaves_no_release_directory(self):
        output, candidates, calls = self.run_packager(failure="signature")
        self.assertEqual(len(calls), 3)
        self.assertFalse(output.exists())
        self.assertEqual(len(list(candidates.glob("*.apk"))), 4)

    def test_incomplete_review_never_reaches_signature_or_output(self):
        self.review["completeCorrespondingSourcesVerified"] = False
        output, _, calls = self.run_packager(failure="review")
        self.assertEqual(calls, [])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
