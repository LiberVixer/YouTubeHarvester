import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from patch_quickjs import patch
from rebuild_quickjs import TARGETS


class QuickJsPatchTest(unittest.TestCase):
    def fixture(self, root, missing=False):
        upstream, bundle, output = (root / name for name in ('upstream.aar', 'bundle.zip', 'output.aar'))
        with zipfile.ZipFile(upstream, 'w') as aar, zipfile.ZipFile(bundle, 'w') as replacements:
            aar.writestr('classes.jar', b'unchanged')
            for abi in TARGETS:
                if not missing or abi != 'x86':
                    aar.writestr(f'jni/{abi}/libqjs.so', b'old')
                replacements.writestr(f'{abi}/libqjs.so', b'\x7fELF' + abi.encode())
        return upstream, bundle, output

    def test_replaces_exactly_four_executables_and_preserves_java(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream, bundle, output = self.fixture(Path(directory))
            patch(upstream, bundle, output, hashlib.sha256(bundle.read_bytes()).hexdigest())
            with zipfile.ZipFile(output) as aar:
                self.assertEqual(b'unchanged', aar.read('classes.jar'))
                for abi in TARGETS:
                    self.assertEqual(b'\x7fELF' + abi.encode(), aar.read(f'jni/{abi}/libqjs.so'))

    def test_hash_mismatch_never_changes_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream, bundle, output = self.fixture(Path(directory))
            output.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                patch(upstream, bundle, output, '0' * 64)
            self.assertEqual(b'keep', output.read_bytes())

    def test_missing_abi_preserves_existing_output_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream, bundle, output = self.fixture(Path(directory), missing=True)
            output.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                patch(upstream, bundle, output, hashlib.sha256(bundle.read_bytes()).hexdigest())
            self.assertEqual(b'keep', output.read_bytes())
            self.assertFalse(output.with_suffix('.aar.part').exists())
