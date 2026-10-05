import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from package_controlled_payloads import Entry, closure, link_target, load_build, make_zip, merge, resolve, safe_name, validate_media_api


def elf(machine=3):
    data = bytearray(64)
    data[:6] = b"\x7fELF\x01\x01"
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)


class ControlledPayloadTests(unittest.TestCase):
    @patch("package_controlled_payloads.elf_dependencies", return_value=["libmediandk.so"])
    def test_platform_media_ndk_is_not_shadowed_by_termux_shim(self, unused):
        roots = {"usr/bin/ffmpeg": Entry(elf(), "ffmpeg")}
        pool = {**roots, "usr/lib/libmediandk.so": Entry(elf(), "termux-shim")}
        self.assertEqual(closure(pool, roots, "i686"), roots)

    @patch("package_controlled_payloads.dynamic_symbols")
    def test_media_imports_must_exist_at_minimum_android_api(self, symbols):
        symbols.side_effect = [({"AMediaCodec_start"}, set()),
                               ({"AMediaCodec_start"}, set()),
                               (set(), {"AMediaCodec_start"})]
        payload = {"usr/bin/ffmpeg": Entry(elf(), "ffmpeg")}
        self.assertEqual(validate_media_api(payload, Entry(elf(), "shim"), elf()), ["AMediaCodec_start"])
        symbols.side_effect = [({"AMediaCodec_start"}, set()), (set(), set()),
                               (set(), {"AMediaCodec_start"})]
        with self.assertRaisesRegex(ValueError, "API coverage failed"):
            validate_media_api(payload, Entry(elf(), "shim"), elf())

    def test_unsafe_paths(self):
        for name in ("/etc/passwd", "usr/../outside"):
            with self.assertRaises(ValueError):
                safe_name(name)

    def test_unsafe_and_cyclic_links(self):
        for target in ("/usr/lib/liba.so", "../../outside"):
            with self.assertRaises(ValueError):
                link_target("usr/lib/liba.so", Entry(target.encode(), "pkg", True))
        with self.assertRaises(ValueError):
            resolve({"usr/lib/liba.so": Entry(b"liba.so", "pkg", True)}, "usr/lib/liba.so")
        roots = {"usr/lib/liba.so": Entry(b"liba.so", "pkg", True)}
        with self.assertRaises(ValueError):
            closure(roots, roots, "i686")

    def test_conflicting_files(self):
        entries = {"usr/lib/liba.so": Entry(b"original", "a")}
        with self.assertRaises(ValueError):
            merge(entries, "usr/lib/liba.so", Entry(b"different", "b"))
        merge(entries, "usr/lib/liba.so", Entry(b"original", "b"))
        self.assertEqual(entries["usr/lib/liba.so"].package, "a")

    @patch("package_controlled_payloads.elf_dependencies", return_value=["libc.so", "liba.so"])
    def test_dependency_and_symlink_closure(self, unused):
        root = {"usr/bin/python3.12": Entry(elf(), "python")}
        pool = {**root, "usr/lib/liba.so": Entry(b"liba.so.1", "liba", True),
                "usr/lib/liba.so.1": Entry(b"library", "liba")}
        self.assertEqual(set(closure(pool, root, "i686")), set(pool))
        with self.assertRaises(ValueError):
            closure(root, root, "i686")

    @patch("package_controlled_payloads.elf_dependencies", return_value=[])
    def test_wrong_machine_rejected(self, unused):
        roots = {"usr/bin/python3.12": Entry(elf(40), "python")}
        with self.assertRaises(ValueError):
            closure(roots, roots, "i686")

    def test_deterministic_zip_with_parent_dirs_before_links(self):
        entries = {"usr/lib/liba.so": Entry(b"liba.so.1", "liba", True),
                   "usr/lib/liba.so.1": Entry(b"library", "liba")}
        data = make_zip(entries)
        self.assertEqual(data, make_zip(dict(reversed(list(entries.items())))))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            self.assertLess(names.index("usr/lib/"), names.index("usr/lib/liba.so"))
            self.assertTrue(stat.S_ISLNK(archive.getinfo("usr/lib/liba.so").external_attr >> 16))
            self.assertEqual(archive.read("usr/lib/liba.so"), b"liba.so.1")

    def test_build_manifest_identity_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            info = {"architecture": "i686", "buildExitCode": 0, "lock": {}, "files": []}
            manifest = folder / "BUILD-INFO-runtime.json"
            manifest.write_text(json.dumps(info))
            expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
            self.assertEqual(load_build(folder, expected, "i686", {}), {})
            for wrong_hash, wrong_arch in (("0" * 64, "i686"), (expected, "arm")):
                with self.assertRaises(ValueError):
                    load_build(folder, wrong_hash, wrong_arch, {})


if __name__ == "__main__":
    unittest.main()
