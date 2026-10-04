import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from runtime_inventory import inventory


def bundle(entries):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return result.getvalue()


class RuntimeInventoryTest(unittest.TestCase):
    def inspect(self, payload, **kwargs):
        with tempfile.TemporaryDirectory() as root:
            apk = Path(root) / 'qa.apk'
            apk.write_bytes(payload)
            return inventory(apk, inspect_elf=False, **kwargs)

    def test_nested_bytes_metadata_and_scope(self):
        metadata = b'Name: QA-runtime\nVersion: 1.2\nLicense: MIT\n\n'
        runtime = bundle([('usr/lib/qa.dist-info/METADATA', metadata), ('usr/lib/libqa.so', b'\x7fELFqa')])
        payload = bundle([('lib/x86_64/libpython.zip.so', runtime), ('classes.dex', b'ignored')])
        result = self.inspect(payload)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), result['apkSha256'])
        self.assertFalse(result['correspondingSourcesVerified'])
        self.assertEqual(3, len(result['entries']))
        records = {entry['path']: entry for entry in result['entries']}
        prefix = 'lib/x86_64/libpython.zip.so!'
        self.assertEqual('1.2', records[prefix + 'usr/lib/qa.dist-info/METADATA']['pythonMetadata']['Version'])
        self.assertEqual('ELF', records[prefix + 'usr/lib/libqa.so']['kind'])
        self.assertEqual(hashlib.sha256(metadata).hexdigest(),
                         records[prefix + 'usr/lib/qa.dist-info/METADATA']['sha256'])

    def test_expanded_size_limit(self):
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.inspect(bundle([('lib/x86/libqa.so', b'12345')]), max_bytes=4)

    def test_nesting_limit(self):
        payload = b'leaf'
        for _ in range(5):
            payload = bundle([('lib/runtime.zip', payload)])
        with self.assertRaisesRegex(ValueError, 'depth'):
            self.inspect(payload)


if __name__ == '__main__':
    unittest.main()
